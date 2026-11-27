# Initial minimal-schema migration for the production financial/contacts workflow.
import uuid
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator
import intake.crypto

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Lead",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                                        editable=False, serialize=False)),
                ("request_key", models.UUIDField(unique=True, editable=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now,
                                                      editable=False, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("stage", models.CharField(max_length=12, default="new", db_index=True,
                    choices=[("new","Новая"),("review","В работе"),
                             ("quotes","Сбор предложений"),("compare","Сравнение"),
                             ("closed","Завершена")])),
                ("assigned_to",models.ForeignKey(
                    blank=True,null=True,on_delete=models.PROTECT,
                    related_name="assigned_leasing_leads",to=settings.AUTH_USER_MODEL,
                )),
                ("client_name", intake.crypto.EncryptedTextField()),
                ("phone", intake.crypto.EncryptedTextField()),
                ("email", intake.crypto.EncryptedTextField(blank=True, default="")),
                ("company", intake.crypto.EncryptedTextField(blank=True, default="")),
                ("inn", intake.crypto.EncryptedTextField(blank=True, default="")),
                ("message", intake.crypto.EncryptedTextField(blank=True, default="")),
                ("asset_type", models.CharField(max_length=32)),
                ("asset_price", models.DecimalField(max_digits=14, decimal_places=2)),
                ("advance", models.DecimalField(max_digits=14, decimal_places=2)),
                ("term_months", models.PositiveSmallIntegerField(
                    validators=[MinValueValidator(12),MaxValueValidator(84)])),
                ("vat_basis", models.CharField(max_length=20, default="included")),
                ("consent_version", models.CharField(max_length=80)),
                ("consent_text_sha256", models.CharField(max_length=64)),
                ("consent_at", models.DateTimeField(default=django.utils.timezone.now,
                                                      editable=False)),
                ("source_ip_digest", models.CharField(max_length=64)),
                ("source", models.CharField(max_length=32, default="site", editable=False)),
            ],
            options={
                "verbose_name":"Заявка",
                "verbose_name_plural":"Заявки",
                "ordering":["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CallbackRequest",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                                        editable=False, serialize=False)),
                ("request_key", models.UUIDField(unique=True, editable=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now,
                                                      editable=False, db_index=True)),
                ("stage", models.CharField(max_length=12, default="new", db_index=True,
                    choices=[("new","Ожидает звонка"),("contacted","Связались"),
                             ("closed","Завершена")])),
                ("name", intake.crypto.EncryptedTextField(blank=True, default="")),
                ("phone", intake.crypto.EncryptedTextField()),
                ("consent_version", models.CharField(max_length=80)),
                ("consent_text_sha256", models.CharField(max_length=64)),
                ("consent_at", models.DateTimeField(default=django.utils.timezone.now,
                                                      editable=False)),
                ("source_ip_digest", models.CharField(max_length=64)),
            ],
            options={
                "verbose_name":"Обратный звонок",
                "verbose_name_plural":"Обратные звонки",
                "ordering":["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SubmissionAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ip_digest", models.CharField(max_length=64)),
                ("window_at", models.DateTimeField()),
                ("count", models.PositiveSmallIntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name="Quote",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                                        editable=False, serialize=False)),
                ("source_document_id", models.CharField(max_length=64)),
                ("offer_id", models.CharField(max_length=64)),
                ("lessor_name", models.CharField(max_length=160)),
                ("received_on", models.DateField()),
                ("valid_until", models.DateField()),
                ("verified_by_broker", models.BooleanField(default=False)),
                ("monthly_payment", models.DecimalField(
                    max_digits=14, decimal_places=2, blank=True, null=True)),
                ("buyout", models.DecimalField(
                    max_digits=14, decimal_places=2, blank=True, null=True)),
                ("upfront_fee", models.DecimalField(
                    max_digits=14, decimal_places=2, blank=True, null=True)),
                ("recurring_monthly_fee", models.DecimalField(
                    max_digits=14, decimal_places=2, blank=True, null=True)),
                ("insurance_total", models.DecimalField(
                    max_digits=14, decimal_places=2, blank=True, null=True)),
                ("other_costs", models.DecimalField(
                    max_digits=14, decimal_places=2, blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now,
                                                      editable=False)),
                ("lead", models.ForeignKey(on_delete=models.PROTECT,related_name="quotes",
                                          to="intake.lead")),
            ],
            options={
                "verbose_name":"КП лизингодателя",
                "verbose_name_plural":"КП лизингодателей",
                "ordering":["created_at"],
            },
        ),
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                                        editable=False, serialize=False)),
                ("at", models.DateTimeField(default=django.utils.timezone.now,
                                           editable=False)),
                ("action", models.CharField(max_length=48)),
                ("actor", models.CharField(max_length=64)),
                ("details", models.CharField(max_length=180,blank=True)),
                ("lead", models.ForeignKey(on_delete=models.PROTECT,related_name="audit_events",
                                          to="intake.lead")),
            ],
            options={
                "verbose_name":"Событие аудита",
                "verbose_name_plural":"События аудита",
                "ordering":["at"],
            },
        ),
        migrations.AddConstraint(
            model_name="submissionattempt",
            constraint=models.UniqueConstraint(fields=("ip_digest","window_at"),
                                               name="unique_ip_window"),
        ),
        migrations.AddConstraint(
            model_name="quote",
            constraint=models.UniqueConstraint(fields=("lead","offer_id"),
                                               name="unique_lead_offer_id"),
        ),
        migrations.AddConstraint(
            model_name="quote",
            constraint=models.UniqueConstraint(fields=("lead","source_document_id"),
                                               name="unique_lead_source_id"),
        ),
    ]
