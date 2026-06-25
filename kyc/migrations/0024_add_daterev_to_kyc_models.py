from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kyc", "0023_expand_group_quality_rules"),
    ]

    operations = [
        migrations.AddField(
            model_name="kyc_pm",
            name="DATEREV",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="kyc_pp",
            name="DATEREV",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
