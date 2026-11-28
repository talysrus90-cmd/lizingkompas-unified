"""Production contact-intake and broker quote models.

Only staff may read leads. Never expose row IDs or sensitive text over public API.
No client documents or credit bureau decisions are stored by these models.
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
