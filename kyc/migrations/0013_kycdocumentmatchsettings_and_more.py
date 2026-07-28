                                                

from django.db import migrations, models


def create_default_match_settings(apps, schema_editor):
    KycDocumentMatchSettings = apps.get_model('kyc', 'KycDocumentMatchSettings')
    KycDocumentMatchSettings.objects.get_or_create(
        name='Parametrage standard',
        defaults={
            'birth_date_weight': 35,
            'document_validity_weight': 35,
            'nationality_weight': 30,
            'combination_threshold': 65,
            'active': True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0012_kycdocumentextraction_pays_delivrance'),
    ]

    operations = [
        migrations.CreateModel(
            name='KycDocumentMatchSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Parametrage standard', max_length=80, unique=True)),
                ('birth_date_weight', models.PositiveSmallIntegerField(default=35, verbose_name='Poids date de naissance')),
                ('document_validity_weight', models.PositiveSmallIntegerField(default=35, verbose_name='Poids date de validite')),
                ('nationality_weight', models.PositiveSmallIntegerField(default=30, verbose_name='Poids nationalite')),
                ('combination_threshold', models.PositiveSmallIntegerField(default=65, verbose_name='Seuil de correspondance combinee')),
                ('active', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Parametrage de correspondance KYC ID',
                'verbose_name_plural': 'Parametrage des correspondances KYC ID',
            },
        ),
        migrations.RenameIndex(
            model_name='kycdocumentextraction',
            new_name='kyc_kycdocu_pays_de_1eead0_idx',
            old_name='kyc_kycdocu_pays_de_20d3a5_idx',
        ),
        migrations.RunPython(create_default_match_settings, migrations.RunPython.noop),
    ]
