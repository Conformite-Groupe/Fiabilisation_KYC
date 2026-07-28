                                                

import django.core.validators
from django.db import migrations, models


def normalize_match_settings(apps, schema_editor):
    KycDocumentMatchSettings = apps.get_model('kyc', 'KycDocumentMatchSettings')
    for settings in KycDocumentMatchSettings.objects.all():
        total = (
            settings.birth_date_weight
            + settings.document_validity_weight
            + settings.birth_place_weight
            + settings.nationality_weight
        )
        if total > 100:
            settings.nationality_weight = max(0, settings.nationality_weight - (total - 100))
            settings.save(update_fields=['nationality_weight'])


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0014_kycdocumentmatchsettings_birth_place_weight'),
    ]

    operations = [
        migrations.AlterField(
            model_name='kycdocumentmatchsettings',
            name='birth_date_weight',
            field=models.PositiveSmallIntegerField(default=35, validators=[django.core.validators.MaxValueValidator(100)], verbose_name='Poids date de naissance'),
        ),
        migrations.AlterField(
            model_name='kycdocumentmatchsettings',
            name='birth_place_weight',
            field=models.PositiveSmallIntegerField(default=10, validators=[django.core.validators.MaxValueValidator(100)], verbose_name='Poids lieu de naissance'),
        ),
        migrations.AlterField(
            model_name='kycdocumentmatchsettings',
            name='combination_threshold',
            field=models.PositiveSmallIntegerField(default=65, validators=[django.core.validators.MaxValueValidator(100)], verbose_name='Seuil de correspondance combinee'),
        ),
        migrations.AlterField(
            model_name='kycdocumentmatchsettings',
            name='document_validity_weight',
            field=models.PositiveSmallIntegerField(default=35, validators=[django.core.validators.MaxValueValidator(100)], verbose_name='Poids date de validite'),
        ),
        migrations.AlterField(
            model_name='kycdocumentmatchsettings',
            name='nationality_weight',
            field=models.PositiveSmallIntegerField(default=20, validators=[django.core.validators.MaxValueValidator(100)], verbose_name='Poids nationalite'),
        ),
        migrations.RunPython(normalize_match_settings, migrations.RunPython.noop),
    ]
