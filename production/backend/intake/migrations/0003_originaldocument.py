import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("intake", "0002_quote_source_terms"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="OriginalDocument",
            fields=[
                ("id", models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now,editable=False)),
                ("sha256", models.CharField(max_length=64,editable=False)),
                ("byte_count", models.PositiveIntegerField(editable=False)),
                ("ciphertext", models.BinaryField(editable=False)),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="original_documents",to="intake.lead")),
                ("quote", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name="original_document",to="intake.quote")),
                ("uploaded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering":["-created_at"],"verbose_name":"Оригинал КП","verbose_name_plural":"Оригиналы КП",
                     "constraints":[models.UniqueConstraint(fields=("lead","sha256"),name="unique_case_original_hash")]},
        )
    ]
