                                               

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0045_kycdocumentmatchsettings_firstname_weight_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='kycdocumentmatchsettings',
            name='pm_firstname_field',
            field=models.CharField(choices=[('INTITULE_COMPTE', 'INTITULE_COMPTE (Raison sociale / Denomination)'), ('ACTIONNAIRE', 'ACTIONNAIRE (Actionnaire)'), ('MANDATAIRE', 'MANDATAIRE (Mandataire)')], default='INTITULE_COMPTE', max_length=50, verbose_name='Champ prenom (KYC PM)'),
        ),
        migrations.AlterField(
            model_name='kycdocumentmatchsettings',
            name='pm_name_field',
            field=models.CharField(choices=[('INTITULE_COMPTE', 'INTITULE_COMPTE (Raison sociale / Denomination)'), ('ACTIONNAIRE', 'ACTIONNAIRE (Actionnaire)'), ('MANDATAIRE', 'MANDATAIRE (Mandataire)')], default='INTITULE_COMPTE', max_length=50, verbose_name='Champ nom (KYC PM)'),
        ),
        migrations.AlterField(
            model_name='kycdocumentmatchsettings',
            name='pp_firstname_field',
            field=models.CharField(choices=[('INTITULE_COMPTE', 'INTITULE_COMPTE (Nom & Prenom)'), ('EMPLOYEUR', 'EMPLOYEUR (Employeur)')], default='INTITULE_COMPTE', max_length=50, verbose_name='Champ prenom (KYC PP)'),
        ),
        migrations.AlterField(
            model_name='kycdocumentmatchsettings',
            name='pp_name_field',
            field=models.CharField(choices=[('INTITULE_COMPTE', 'INTITULE_COMPTE (Nom & Prenom)'), ('EMPLOYEUR', 'EMPLOYEUR (Employeur)')], default='INTITULE_COMPTE', max_length=50, verbose_name='Champ nom (KYC PP)'),
        ),
    ]
