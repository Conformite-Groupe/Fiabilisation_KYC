from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kyc", "0028_kycfieldvisibilityconfig"),
    ]

    operations = [
        migrations.AlterField(
            model_name="kycfieldvisibilityconfig",
            name="client_type",
            field=models.CharField(choices=[("pp", "Particuliers (PP)"), ("pm", "Entreprises (PM)")], max_length=2),
        ),
        migrations.AddField(
            model_name="kycfieldvisibilityconfig",
            name="filiales",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
