"""Production contact-intake and broker quote models.

Only staff may read leads. Never expose row IDs or sensitive text over public API.
Private original documents are stored separately as authenticated ciphertext. No credit bureau decisions.
"""
import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from broker.offer_comparison import Scenario, ID
from .forms import VAT_BASES
from django.utils import timezone
from .crypto import EncryptedTextField

class Lead(models.Model):
    class Stage(models.TextChoices):
        NEW = "new", "Новая"
        REVIEW = "review", "В работе"
        QUOTES = "quotes", "Сбор предложений"
        COMPARE = "compare", "Сравнение"
        CLOSED = "closed", "Завершена"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_key = models.UUIDField(unique=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    stage = models.CharField(max_length=12, choices=Stage.choices, default=Stage.NEW, db_index=True)
    assigned_to = models.ForeignKey(
        "auth.User",null=True,blank=True,on_delete=models.PROTECT,
        related_name="assigned_leasing_leads"
    )
    client_name = EncryptedTextField()
    phone = EncryptedTextField()
    email = EncryptedTextField(blank=True, default="")
    company = EncryptedTextField(blank=True, default="")
    inn = EncryptedTextField(blank=True, default="")
    message = EncryptedTextField(blank=True, default="")
    asset_type = models.CharField(max_length=32)
    asset_price = models.DecimalField(max_digits=14, decimal_places=2)
    advance = models.DecimalField(max_digits=14, decimal_places=2)
    term_months = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(12), MaxValueValidator(84)]
    )
    vat_basis = models.CharField(max_length=20, default="included")
    consent_version = models.CharField(max_length=80)
    consent_text_sha256 = models.CharField(max_length=64)
    consent_at = models.DateTimeField(default=timezone.now, editable=False)
    source_ip_digest = models.CharField(max_length=64)
    source = models.CharField(max_length=32, default="site", editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"

    def __str__(self):
        return f"Заявка {str(self.pk)[:8]} / {self.stage}"

class Quote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="quotes")
    source_document_id = models.CharField(max_length=64)
    offer_id = models.CharField(max_length=64)
    lessor_name = models.CharField(max_length=160)
    received_on = models.DateField()
    valid_until = models.DateField()
    verified_by_broker = models.BooleanField(default=False)
    # Independently recorded source terms. Existing offers intentionally retain
    # NULLs until a broker verifies the actual original, never backfilled by guess.
    quoted_asset_price = models.DecimalField("Стоимость имущества по КП",max_digits=14,decimal_places=2,null=True,blank=True)
    quoted_advance = models.DecimalField("Аванс по КП",max_digits=14,decimal_places=2,null=True,blank=True)
    quoted_term_months = models.PositiveSmallIntegerField("Срок по КП, мес.",null=True,blank=True,validators=[MinValueValidator(12),MaxValueValidator(84)])
    quoted_vat_basis = models.CharField("НДС по КП",max_length=20,choices=VAT_BASES,blank=True,default="")
    payment_schedule = models.JSONField(default=dict,blank=True,editable=False)
    monthly_payment = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    buyout = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    upfront_fee = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    recurring_monthly_fee = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    insurance_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    other_costs = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["lead","offer_id"],name="unique_lead_offer_id"),
            models.UniqueConstraint(fields=["lead","source_document_id"],name="unique_lead_source_id"),
        ]
        ordering = ["created_at"]
        verbose_name = "КП лизингодателя"
        verbose_name_plural = "КП лизингодателей"

    def source_scenario(self):
        values=(self.quoted_asset_price,self.quoted_advance,self.quoted_term_months,self.quoted_vat_basis)
        if any(x is None or x == "" for x in values):
            return None
        return Scenario(*values)

    def clean(self):
        super().clean()
        values=(self.quoted_asset_price,self.quoted_advance,self.quoted_term_months,self.quoted_vat_basis)
        supplied=[x is not None and x != "" for x in values]
        if any(supplied):
            if not all(supplied):
                raise ValidationError("Укажите все четыре условия КП либо оставьте их неизвестными.")
            try:
                self.source_scenario()
            except ValueError as exc:
                raise ValidationError("Недопустимые финансовые условия КП.") from exc
        for key in ("offer_id","source_document_id"):
            if not ID.fullmatch(getattr(self,key) or ""):
                raise ValidationError({key:"3–64 латинских символа, цифры, дефис или подчёркивание."})
        if self.received_on and self.valid_until and self.valid_until < self.received_on:
            raise ValidationError({"valid_until":"Срок действия раньше даты получения."})
        for key in ("monthly_payment","buyout","upfront_fee","recurring_monthly_fee","insurance_total","other_costs"):
            value=getattr(self,key)
            if value is not None and value < 0:
                raise ValidationError({key:"Сумма не может быть отрицательной."})

    def __str__(self):
        return f"{self.lessor_name} / {self.offer_id}"

class SubmissionAttempt(models.Model):
    """Aggregate rate-limit record. IP addresses are HMAC-hashed, not stored."""
    ip_digest = models.CharField(max_length=64)
    window_at = models.DateTimeField()
    count = models.PositiveSmallIntegerField(default=0)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ip_digest","window_at"],name="unique_ip_window")
        ]

class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="audit_events")
    at = models.DateTimeField(default=timezone.now, editable=False)
    action = models.CharField(max_length=48)
    actor = models.CharField(max_length=64)  # authenticated staff ID or "public_submission"
    details = models.CharField(max_length=180, blank=True)
    class Meta:
        ordering = ["at"]
        verbose_name = "Событие аудита"
        verbose_name_plural = "События аудита"

class CallbackRequest(models.Model):
    """Encrypted callback request; no unneeded client asset/financial details."""

    class Stage(models.TextChoices):
        NEW = "new", "Ожидает звонка"
        CONTACTED = "contacted", "Связались"
        CLOSED = "closed", "Завершена"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_key = models.UUIDField(unique=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    stage = models.CharField(max_length=12, choices=Stage.choices, default=Stage.NEW, db_index=True)
    name = EncryptedTextField(blank=True, default="")
    phone = EncryptedTextField()
    consent_version = models.CharField(max_length=80)
    consent_text_sha256 = models.CharField(max_length=64)
    consent_at = models.DateTimeField(default=timezone.now, editable=False)
    source_ip_digest = models.CharField(max_length=64)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Обратный звонок"
        verbose_name_plural = "Обратные звонки"

    def __str__(self):
        return f"Обратный звонок {str(self.pk)[:8]} / {self.stage}"


class OriginalDocument(models.Model):
    """Bounded, encrypted PDF original. No user filename or public storage URL."""
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    lead = models.ForeignKey(Lead,on_delete=models.PROTECT,related_name="original_documents")
    quote = models.OneToOneField(Quote,on_delete=models.PROTECT,related_name="original_document")
    uploaded_by = models.ForeignKey("auth.User",on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now,editable=False)
    sha256 = models.CharField(max_length=64,editable=False)
    byte_count = models.PositiveIntegerField(editable=False)
    ciphertext = models.BinaryField(editable=False)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["lead","sha256"],name="unique_case_original_hash")]
        ordering = ["-created_at"]
        verbose_name = "Оригинал КП"
        verbose_name_plural = "Оригиналы КП"


class LenderRequest(models.Model):
    """Internal tracking of a manually submitted financial request; no transmission."""
    class State(models.TextChoices):
        DRAFT = "draft", "Подготовлен"
        SENT = "sent", "Отправлен вручную"
        REVIEW = "review", "Рассматривается"
        OFFER = "offer", "КП получено"
        DECLINED = "declined", "Отказ"
        CANCELLED = "cancelled", "Отменён"

    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    lead = models.ForeignKey(Lead,on_delete=models.PROTECT,related_name="lender_requests")
    lessor_name = models.CharField(max_length=160)
    lessor_key = models.CharField(max_length=320,editable=False)
    state = models.CharField(max_length=12,choices=State.choices,default=State.DRAFT)
    created_at = models.DateTimeField(default=timezone.now,editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    due_on = models.DateField(null=True,blank=True)
    sent_at = models.DateTimeField(null=True,blank=True,editable=False)
    responded_at = models.DateTimeField(null=True,blank=True,editable=False)
    quote = models.OneToOneField(Quote,null=True,blank=True,on_delete=models.PROTECT,related_name="lender_request")
    version = models.PositiveIntegerField(default=0,editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lead","lessor_key"],name="unique_case_lender_request")]
        ordering = ["-created_at","id"]
        verbose_name = "Запрос лизингодателю"
        verbose_name_plural = "Запросы лизингодателям"


class BrokerTask(models.Model):
    """Structured, case-scoped work item; no free text or external side effects."""
    class Kind(models.TextChoices):
        CALL = "call", "Связаться с клиентом"
        COLLECT = "collect", "Собрать КП"
        FOLLOWUP = "followup", "Уточнить ответ лизингодателя"
        VERIFY = "verify", "Сверить условия КП"
        DOCUMENT = "document", "Проверить документы"
        CONTRACT = "contract", "Проверить договор"
        REVIEW = "review", "Проверить сделку"

    class State(models.TextChoices):
        OPEN = "open", "К выполнению"
        DONE = "done", "Выполнено"
        CANCELLED = "cancelled", "Отменено"

    class Priority(models.IntegerChoices):
        HIGH = 1, "Высокий"
        NORMAL = 2, "Обычный"
        LOW = 3, "Низкий"

    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    lead = models.ForeignKey(Lead,on_delete=models.PROTECT,related_name="broker_tasks")
    kind = models.CharField(max_length=12,choices=Kind.choices)
    state = models.CharField(max_length=12,choices=State.choices,default=State.OPEN)
    priority = models.PositiveSmallIntegerField(choices=Priority.choices,default=Priority.NORMAL)
    due_on = models.DateField(db_index=True)
    created_at = models.DateTimeField(default=timezone.now,editable=False)
    completed_at = models.DateTimeField(null=True,blank=True,editable=False)
    version = models.PositiveIntegerField(default=0,editable=False)

    class Meta:
        ordering = ["due_on","priority","id"]
        constraints = [models.UniqueConstraint(fields=["lead","kind"],condition=models.Q(state="open"),name="unique_open_case_task_kind")]
        verbose_name = "Задача брокера"
        verbose_name_plural = "Задачи брокера"


class ClientPortalControl(models.Model):
    """Single server-side switch, OFF unless explicitly activated by operator."""
    id = models.PositiveSmallIntegerField(primary_key=True,default=1,editable=False)
    enabled = models.BooleanField("Клиентский кабинет включён",default=False)
    revision = models.UUIDField(default=uuid.uuid4,editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(id=1),name="singleton_client_portal")]
        verbose_name="Выключатель клиентского кабинета"
        verbose_name_plural="Выключатель клиентского кабинета"


class ClientCaseAccess(models.Model):
    """Explicit operator grant; never infer identity from a phone or email."""
    user = models.ForeignKey("auth.User",on_delete=models.PROTECT,limit_choices_to={"is_staff":False,"is_superuser":False,"is_active":True})
    lead = models.ForeignKey(Lead,on_delete=models.PROTECT,limit_choices_to=~models.Q(source="broker_internal"))
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now,editable=False)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["user","lead"],name="unique_client_case_access")]
        verbose_name="Доступ клиента к сделке"
        verbose_name_plural="Доступы клиентов к сделкам"
    def clean(self):
        super().clean()
        if self.user_id and (self.user.is_staff or self.user.is_superuser or not self.user.is_active):
            raise ValidationError({"user":"Нужна активная клиентская учётная запись без прав сотрудников."})
        if self.lead_id and (self.lead.source=="broker_internal" or not self.lead.consent_version):
            raise ValidationError({"lead":"Внутренние расчёты или заявки без согласия недоступны клиентам."})


class ContractReview(models.Model):
    """Human review of one identified contract revision, not a legal opinion."""
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    lead = models.ForeignKey(Lead,on_delete=models.PROTECT,related_name="contract_reviews")
    source_sha256 = models.CharField(max_length=64)
    checklist_version = models.PositiveSmallIntegerField(default=1,editable=False)
    created_at = models.DateTimeField(default=timezone.now,editable=False)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["lead","source_sha256"],name="unique_case_contract_revision")]
        ordering=["-created_at","id"]


class ContractReviewItem(models.Model):
    class State(models.TextChoices):
        UNKNOWN = "unknown", "Не проверено"
        OK = "ok", "Проверено, замечаний нет"
        RISK = "risk", "Требует внимания"
        MISSING = "missing", "Условие не найдено"

    review = models.ForeignKey(ContractReview,on_delete=models.PROTECT,related_name="items")
    topic = models.CharField(max_length=32)
    state = models.CharField(max_length=12,choices=State.choices,default=State.UNKNOWN)
    page = models.PositiveIntegerField(null=True,blank=True)
    reviewed_by = models.ForeignKey("auth.User",null=True,on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(null=True)
    version = models.PositiveIntegerField(default=0,editable=False)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["review","topic"],name="unique_contract_review_topic")]
