import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations,models

class Migration(migrations.Migration):
    dependencies=[("intake","0008_quote_payment_schedule"),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.AlterField(model_name="lead",name="stage",field=models.CharField(choices=[("new","Новая"),("review","В работе"),("quotes","Сбор предложений"),("compare","Сравнение"),("closed","Закрыта (выдача отдельно)")],db_index=True,default="new",max_length=12)),
        migrations.CreateModel(name="DeliveryConfirmation",fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("delivered_on",models.DateField(db_index=True)),
            ("evidence_sha256",models.CharField(max_length=64)),
            ("confirmed_at",models.DateTimeField(default=django.utils.timezone.now,editable=False)),
            ("confirmed_by",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
            ("lead",models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name="delivery_confirmation",to="intake.lead"))
        ],options={"verbose_name":"Подтверждение выдачи имущества","verbose_name_plural":"Подтверждения выдачи имущества"})
    ]
