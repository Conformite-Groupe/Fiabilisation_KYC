                                               

import django.core.validators
from django.db import migrations, models


def consolidate_forward(apps, schema_editor):
    """Recopie les anciens poids/champs vers les champs consolides nom & prenom."""
    Settings = apps.get_model('kyc', 'KycDocumentMatchSettings')
    for obj in Settings.objects.all():
        obj.fullname_weight = min(100, (obj.name_weight or 0) + (obj.firstname_weight or 0))
        obj.pp_fullname_field = obj.pp_name_field or 'INTITULE_COMPTE'
        obj.pm_fullname_field = obj.pm_name_field or 'INTITULE_COMPTE'
        obj.save(update_fields=['fullname_weight', 'pp_fullname_field', 'pm_fullname_field'])


def consolidate_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0051_alter_kycmatchdecision_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='kycdocumentmatchsettings',
            name='fullname_weight',
            field=models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(100)], verbose_name='Poids nom & prenom'),
        ),
        migrations.AddField(
            model_name='kycdocumentmatchsettings',
            name='pm_fullname_field',
            field=models.CharField(choices=[('INTITULE_COMPTE', 'INTITULE_COMPTE (Raison sociale / Denomination)'), ('ACTIONNAIRE', 'ACTIONNAIRE (Actionnaire)'), ('MANDATAIRE', 'MANDATAIRE (Mandataire)')], default='INTITULE_COMPTE', max_length=50, verbose_name='Champ nom & prenom (KYC PM)'),
        ),
        migrations.AddField(
            model_name='kycdocumentmatchsettings',
            name='pp_fullname_field',
            field=models.CharField(choices=[('INTITULE_COMPTE', 'INTITULE_COMPTE (Nom & Prenom)'), ('EMPLOYEUR', 'EMPLOYEUR (Employeur)')], default='INTITULE_COMPTE', max_length=50, verbose_name='Champ nom & prenom (KYC PP)'),
        ),
        migrations.RunPython(consolidate_forward, consolidate_backward),
        migrations.RemoveField(
            model_name='kycdocumentmatchsettings',
            name='firstname_weight',
        ),
        migrations.RemoveField(
            model_name='kycdocumentmatchsettings',
            name='name_weight',
        ),
        migrations.RemoveField(
            model_name='kycdocumentmatchsettings',
            name='pm_firstname_field',
        ),
        migrations.RemoveField(
            model_name='kycdocumentmatchsettings',
            name='pm_name_field',
        ),
        migrations.RemoveField(
            model_name='kycdocumentmatchsettings',
            name='pp_firstname_field',
        ),
        migrations.RemoveField(
            model_name='kycdocumentmatchsettings',
            name='pp_name_field',
        ),
    ]
