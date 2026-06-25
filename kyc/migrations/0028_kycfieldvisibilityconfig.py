from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kyc", "0027_remove_kyccompletenesscalculation_calculated_by_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="KycFieldVisibilityConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("client_type", models.CharField(choices=[("pp", "Particuliers (PP)"), ("pm", "Entreprises (PM)")], max_length=2, unique=True)),
                ("empty_check_fields", models.JSONField(blank=True, default=list)),
                ("display_fields", models.JSONField(blank=True, default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Configuration champs KYC",
                "verbose_name_plural": "Configurations champs KYC",
            },
        ),
    ]
