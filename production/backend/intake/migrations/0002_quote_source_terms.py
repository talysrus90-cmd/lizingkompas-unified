from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("intake", "0001_initial")]
    operations = [
        migrations.AddField(model_name="quote",name="quoted_asset_price",field=models.DecimalField("Стоимость имущества по КП",blank=True,null=True,max_digits=14,decimal_places=2)),
        migrations.AddField(model_name="quote",name="quoted_advance",field=models.DecimalField("Аванс по КП",blank=True,null=True,max_digits=14,decimal_places=2)),
        migrations.AddField(model_name="quote",name="quoted_term_months",field=models.PositiveSmallIntegerField("Срок по КП, мес.",blank=True,null=True,validators=[django.core.validators.MinValueValidator(12),django.core.validators.MaxValueValidator(84)])),
        migrations.AddField(model_name="quote",name="quoted_vat_basis",field=models.CharField("НДС по КП",blank=True,default="",max_length=20,choices=[("included","НДС включён"),("excluded","Без НДС"),("not_applicable","Не применяется")])),
    ]
