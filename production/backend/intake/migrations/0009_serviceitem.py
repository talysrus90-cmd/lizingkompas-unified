import uuid
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations,models

class Migration(migrations.Migration):
    dependencies=[("intake","0008_quote_payment_schedule")]
    operations=[migrations.CreateModel(
        name="ServiceItem",
        fields=[
            ("id",models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),
            ("kind",models.CharField(choices=[("delivery","Передача имущества"),("insurance","Продление страхования"),("claim","Страховой случай"),("restructure","Изменение графика"),("buyout","Досрочный или плановый выкуп"),("maturity","Окончание договора"),("complaint","Претензионная работа"),("renewal","Повторная сделка"),("disposal","Реализация имущества")],max_length=16)),
            ("state",models.CharField(choices=[("open","К выполнению"),("done","Выполнено"),("cancelled","Отменено")],default="open",max_length=12)),
            ("due_on",models.DateField(db_index=True)),
            ("created_at",models.DateTimeField(default=django.utils.timezone.now,editable=False)),
            ("completed_at",models.DateTimeField(blank=True,editable=False,null=True)),
            ("version",models.PositiveIntegerField(default=0,editable=False)),
            ("lead",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="service_items",to="intake.lead"))
        ],
        options={"ordering":["due_on","id"],"verbose_name":"Сопровождение сделки","verbose_name_plural":"Сопровождение сделок",
                 "constraints":[models.UniqueConstraint(condition=models.Q(state="open"),fields=("lead","kind"),name="unique_open_case_service_kind")]}
    )]
