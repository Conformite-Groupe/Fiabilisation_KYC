                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0058_seed_screening_access'),
    ]

    operations = [
        migrations.AddField(
            model_name='kycfieldvisibilityconfig',
            name='field_labels',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
