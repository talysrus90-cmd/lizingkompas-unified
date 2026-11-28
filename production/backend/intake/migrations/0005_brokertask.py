import uuid
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("intake","0004_lenderrequest")]
    operations = [
        migrations.CreateModel(
            name="BrokerTask",
            fields=[
                ("id",models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
                ("kind",models.CharField(max_length=12,choices=[("call","Связаться с клиентом"),("collect","Собрать КП"),("followup","Уточнить ответ лизингодателя"),("verify","Сверить условия КП"),("document","Проверить документы"),("contract","Проверить договор"),("review","Проверить сделку")])),
                ("state",models.CharField(max_length=12,default="open",choices=[("open","К выполнению"),("done","Выполнено"),("cancelled","Отменено")])),
                ("priority",models.PositiveSmallIntegerField(default=2,choices=[(1,"Высокий"),(2,"Обычный"),(3,"Низкий")])),
                ("due_on",models.DateField(db_index=True)),
                ("created_at",models.DateTimeField(default=django.utils.timezone.now,editable=False)),
                ("completed_at",models.DateTimeField(null=True,blank=True,editable=False)),
                ("version",models.PositiveIntegerField(default=0,editable=False)),
                ("lead",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="broker_tasks",to="intake.lead")),
            ],
            options={"ordering":["due_on","priority","id"],"verbose_name":"Задача брокера","verbose_name_plural":"Задачи брокера",
                     "constraints":[models.UniqueConstraint(fields=("lead","kind"),condition=models.Q(state="open"),name="unique_open_case_task_kind")]},
        )
    ]
