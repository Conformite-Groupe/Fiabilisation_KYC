                                               

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0047_migrate_name_fields_client_to_intitule'),
    ]

    operations = [
        migrations.AddField(
            model_name='kycdocumentmatchsettings',
            name='min_display_score',
            field=models.PositiveSmallIntegerField(default=30, help_text="Une correspondance dont le score est inferieur n'est pas proposee.", validators=[django.core.validators.MaxValueValidator(100)], verbose_name='Score minimum affiche'),
        ),
    ]
