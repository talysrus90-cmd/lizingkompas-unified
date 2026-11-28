import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("intake","0005_brokertask"),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name="ClientPortalControl",fields=[
            ("id",models.PositiveSmallIntegerField(primary_key=True,default=1,editable=False,serialize=False)),
            ("enabled",models.BooleanField("Клиентский кабинет включён",default=False)),
            ("revision",models.UUIDField(default=uuid.uuid4,editable=False)),
            ("updated_at",models.DateTimeField(auto_now=True)),
        ],options={"verbose_name":"Выключатель клиентского кабинета","verbose_name_plural":"Выключатель клиентского кабинета",
                   "constraints":[models.CheckConstraint(condition=models.Q(id=1),name="singleton_client_portal")]}),
        migrations.CreateModel(name="ClientCaseAccess",fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("active",models.BooleanField(default=True)),
            ("created_at",models.DateTimeField(default=django.utils.timezone.now,editable=False)),
            ("user",models.ForeignKey(limit_choices_to={"is_staff":False,"is_superuser":False,"is_active":True},on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
            ("lead",models.ForeignKey(limit_choices_to=~models.Q(source="broker_internal"),on_delete=django.db.models.deletion.PROTECT,to="intake.lead")),
        ],options={"verbose_name":"Доступ клиента к сделке","verbose_name_plural":"Доступы клиентов к сделкам","constraints":[models.UniqueConstraint(fields=("user","lead"),name="unique_client_case_access")]}),
    ]
