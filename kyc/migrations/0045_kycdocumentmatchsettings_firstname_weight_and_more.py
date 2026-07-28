                                               

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0044_kycdocumentextraction_extraction_status_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='kycdocumentmatchsettings',
            name='firstname_weight',
            field=models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(100)], verbose_name='Poids prenom'),
        ),
        migrations.AddField(
            model_name='kycdocumentmatchsettings',
            name='name_weight',
            field=models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(100)], verbose_name='Poids nom'),
        ),
        migrations.AddField(
            model_name='kycdocumentmatchsettings',
            name='pm_firstname_field',
            field=models.CharField(choices=[('CLIENT', 'CLIENT (Raison sociale)'), ('INTITULE_COMPTE', 'INTITULE_COMPTE (Intitule du compte)'), ('ACTIONNAIRE', 'ACTIONNAIRE (Actionnaire)'), ('MANDATAIRE', 'MANDATAIRE (Mandataire)')], default='CLIENT', max_length=50, verbose_name='Champ prenom (KYC PM)'),
        ),
        migrations.AddField(
            model_name='kycdocumentmatchsettings',
            name='pm_name_field',
            field=models.CharField(choices=[('CLIENT', 'CLIENT (Raison sociale)'), ('INTITULE_COMPTE', 'INTITULE_COMPTE (Intitule du compte)'), ('ACTIONNAIRE', 'ACTIONNAIRE (Actionnaire)'), ('MANDATAIRE', 'MANDATAIRE (Mandataire)')], default='CLIENT', max_length=50, verbose_name='Champ nom (KYC PM)'),
        ),
        migrations.AddField(
            model_name='kycdocumentmatchsettings',
            name='pp_firstname_field',
            field=models.CharField(choices=[('CLIENT', 'CLIENT (Nom & Prenom)'), ('INTITULE_COMPTE', 'INTITULE_COMPTE (Intitule du compte)'), ('EMPLOYEUR', 'EMPLOYEUR (Employeur)')], default='CLIENT', max_length=50, verbose_name='Champ prenom (KYC PP)'),
        ),
        migrations.AddField(
            model_name='kycdocumentmatchsettings',
            name='pp_name_field',
            field=models.CharField(choices=[('CLIENT', 'CLIENT (Nom & Prenom)'), ('INTITULE_COMPTE', 'INTITULE_COMPTE (Intitule du compte)'), ('EMPLOYEUR', 'EMPLOYEUR (Employeur)')], default='CLIENT', max_length=50, verbose_name='Champ nom (KYC PP)'),
        ),
    ]
