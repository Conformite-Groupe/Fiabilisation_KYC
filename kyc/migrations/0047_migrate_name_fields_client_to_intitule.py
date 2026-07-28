                                               

from django.db import migrations


def client_to_intitule(apps, schema_editor):
    """CLIENT etant un numero, on bascule les equivalences nom/prenom vers INTITULE_COMPTE."""
    Settings = apps.get_model('kyc', 'KycDocumentMatchSettings')
    for field in ('pp_name_field', 'pp_firstname_field', 'pm_name_field', 'pm_firstname_field'):
        Settings.objects.filter(**{field: 'CLIENT'}).update(**{field: 'INTITULE_COMPTE'})


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0046_alter_kycdocumentmatchsettings_pm_firstname_field_and_more'),
    ]

    operations = [
        migrations.RunPython(client_to_intitule, noop),
    ]
