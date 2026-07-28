                                               

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0034_alter_kyc_pm_client_alter_kyc_pp_client'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dataqualitycondition',
            name='field_name',
            field=models.CharField(choices=[('FILIALE', 'FILIALE'), ('AGENCE', 'AGENCE'), ('LIB_AGENCE', 'LIB_AGENCE'), ('EXPL', 'EXPL'), ('CLIENT', 'CLIENT'), ('CODAPE', 'CODAPE'), ('IDP', 'IDP'), ('PAYNAIS', 'PAYNAIS'), ('PROFESSION', 'PROFESSION'), ('ADRESSE', 'ADRESSE'), ('PAYS_RESID', 'PAYS_RESID'), ('NUMID', 'NUMID'), ('SALAIRE', 'SALAIRE'), ('ORIGINE_REV', 'ORIGINE_REV'), ('DATVALID', 'DATVALID'), ('DATNAIS', 'DATNAIS'), ('TEL', 'TEL'), ('DATOUV', 'DATOUV'), ('PPE', 'PPE'), ('DEVISE', 'DEVISE'), ('RESID', 'RESID'), ('DATEREV', 'DATEREV'), ('RISQUE', 'RISQUE'), ('BOITE_POSTALE', 'BOITE_POSTALE'), ('CONSENT_BIC', 'CONSENT_BIC'), ('EMPLOYEUR', 'EMPLOYEUR'), ('INTITULE_COMPTE', 'INTITULE_COMPTE'), ('LIEU_DELIVRANCE_CIN', 'LIEU_DELIVRANCE_CIN'), ('FILIALE', 'FILIALE'), ('AGENCE', 'AGENCE'), ('LIB_AGENCE', 'LIB_AGENCE'), ('EXPL', 'EXPL'), ('CLIENT', 'CLIENT'), ('AGEC', 'AGEC'), ('CODAPE', 'CODAPE'), ('IDM', 'IDM'), ('RCSNO', 'RCSNO'), ('CAPITAL', 'CAPITAL'), ('CA', 'CA'), ('RESULTAT', 'RESULTAT'), ('ORIGINE_REV', 'ORIGINE_REV'), ('DATOUV', 'DATOUV'), ('TEL', 'TEL'), ('DEVISE', 'DEVISE'), ('RESID', 'RESID'), ('DATEREV', 'DATEREV'), ('PPE', 'PPE'), ('RISQUE', 'RISQUE'), ('ACTIONNAIRE', 'ACTIONNAIRE'), ('ADRESSE_SOCIALE', 'ADRESSE_SOCIALE'), ('BOITE_POSTALE', 'BOITE_POSTALE'), ('CONSENT_BIC', 'CONSENT_BIC'), ('INTITULE_COMPTE', 'INTITULE_COMPTE'), ('MANDATAIRE', 'MANDATAIRE'), ('NUMERO_FISCAL', 'NUMERO_FISCAL'), ('PAYS_JUR', 'PAYS_JUR')], max_length=100),
        ),
        migrations.AlterField(
            model_name='dataqualityrule',
            name='field_name',
            field=models.CharField(choices=[('FILIALE', 'FILIALE'), ('AGENCE', 'AGENCE'), ('LIB_AGENCE', 'LIB_AGENCE'), ('EXPL', 'EXPL'), ('CLIENT', 'CLIENT'), ('CODAPE', 'CODAPE'), ('IDP', 'IDP'), ('PAYNAIS', 'PAYNAIS'), ('PROFESSION', 'PROFESSION'), ('ADRESSE', 'ADRESSE'), ('PAYS_RESID', 'PAYS_RESID'), ('NUMID', 'NUMID'), ('SALAIRE', 'SALAIRE'), ('ORIGINE_REV', 'ORIGINE_REV'), ('DATVALID', 'DATVALID'), ('DATNAIS', 'DATNAIS'), ('TEL', 'TEL'), ('DATOUV', 'DATOUV'), ('PPE', 'PPE'), ('DEVISE', 'DEVISE'), ('RESID', 'RESID'), ('DATEREV', 'DATEREV'), ('RISQUE', 'RISQUE'), ('BOITE_POSTALE', 'BOITE_POSTALE'), ('CONSENT_BIC', 'CONSENT_BIC'), ('EMPLOYEUR', 'EMPLOYEUR'), ('INTITULE_COMPTE', 'INTITULE_COMPTE'), ('LIEU_DELIVRANCE_CIN', 'LIEU_DELIVRANCE_CIN'), ('FILIALE', 'FILIALE'), ('AGENCE', 'AGENCE'), ('LIB_AGENCE', 'LIB_AGENCE'), ('EXPL', 'EXPL'), ('CLIENT', 'CLIENT'), ('AGEC', 'AGEC'), ('CODAPE', 'CODAPE'), ('IDM', 'IDM'), ('RCSNO', 'RCSNO'), ('CAPITAL', 'CAPITAL'), ('CA', 'CA'), ('RESULTAT', 'RESULTAT'), ('ORIGINE_REV', 'ORIGINE_REV'), ('DATOUV', 'DATOUV'), ('TEL', 'TEL'), ('DEVISE', 'DEVISE'), ('RESID', 'RESID'), ('DATEREV', 'DATEREV'), ('PPE', 'PPE'), ('RISQUE', 'RISQUE'), ('ACTIONNAIRE', 'ACTIONNAIRE'), ('ADRESSE_SOCIALE', 'ADRESSE_SOCIALE'), ('BOITE_POSTALE', 'BOITE_POSTALE'), ('CONSENT_BIC', 'CONSENT_BIC'), ('INTITULE_COMPTE', 'INTITULE_COMPTE'), ('MANDATAIRE', 'MANDATAIRE'), ('NUMERO_FISCAL', 'NUMERO_FISCAL'), ('PAYS_JUR', 'PAYS_JUR')], max_length=100),
        ),
    ]
