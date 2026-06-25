from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kyc", "0024_add_daterev_to_kyc_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="kyc_pm",
            name="PPE",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="kyc_pm",
            name="RISQUE",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="kyc_pp",
            name="RISQUE",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
