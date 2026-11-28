from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("intake","0007_contractreview")]
    operations=[migrations.AddField(model_name="quote",name="payment_schedule",field=models.JSONField(default=dict,blank=True,editable=False))]
