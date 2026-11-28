import uuid
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("intake","0003_originaldocument")]
    operations = [
        migrations.CreateModel(
            name="LenderRequest",
            fields=[
                ("id",models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
                ("lessor_name",models.CharField(max_length=160)),
                ("lessor_key",models.CharField(max_length=320,editable=False)),
                ("state",models.CharField(max_length=12,default="draft",choices=[("draft","Подготовлен"),("sent","Отправлен вручную"),("review","Рассматривается"),("offer","КП получено"),("declined","Отказ"),("cancelled","Отменён")])),
                ("created_at",models.DateTimeField(default=django.utils.timezone.now,editable=False)),
                ("updated_at",models.DateTimeField(auto_now=True)),
                ("due_on",models.DateField(null=True,blank=True)),
                ("sent_at",models.DateTimeField(null=True,blank=True,editable=False)),
                ("responded_at",models.DateTimeField(null=True,blank=True,editable=False)),
                ("version",models.PositiveIntegerField(default=0,editable=False)),
                ("lead",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="lender_requests",to="intake.lead")),
                ("quote",models.OneToOneField(null=True,blank=True,on_delete=django.db.models.deletion.PROTECT,related_name="lender_request",to="intake.quote")),
            ],
            options={"ordering":["-created_at","id"],"verbose_name":"Запрос лизингодателю","verbose_name_plural":"Запросы лизингодателям",
                     "constraints":[models.UniqueConstraint(fields=("lead","lessor_key"),name="unique_case_lender_request")]},
        )
    ]
