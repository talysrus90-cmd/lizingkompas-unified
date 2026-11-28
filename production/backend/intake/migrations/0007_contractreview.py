import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("intake","0006_clientportal"),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name="ContractReview",fields=[
            ("id",models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
            ("source_sha256",models.CharField(max_length=64)),
            ("checklist_version",models.PositiveSmallIntegerField(default=1,editable=False)),
            ("created_at",models.DateTimeField(default=django.utils.timezone.now,editable=False)),
            ("lead",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="contract_reviews",to="intake.lead")),
        ],options={"ordering":["-created_at","id"],"constraints":[models.UniqueConstraint(fields=("lead","source_sha256"),name="unique_case_contract_revision")]}),
        migrations.CreateModel(name="ContractReviewItem",fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("topic",models.CharField(max_length=32)),
            ("state",models.CharField(max_length=12,choices=[("unknown","Не проверено"),("ok","Проверено, замечаний нет"),("risk","Требует внимания"),("missing","Условие не найдено")],default="unknown")),
            ("page",models.PositiveIntegerField(null=True,blank=True)),
            ("reviewed_at",models.DateTimeField(null=True)),
            ("version",models.PositiveIntegerField(default=0,editable=False)),
            ("review",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="items",to="intake.contractreview")),
            ("reviewed_by",models.ForeignKey(null=True,on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
        ],options={"constraints":[models.UniqueConstraint(fields=("review","topic"),name="unique_contract_review_topic")]}),
    ]
