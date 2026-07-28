                                               

from django.db import migrations

                                                                            
                                                         
DEFAULT_VALIDATOR_ORGANES = [
    "Conformité",
    "Conformité Groupe",
    "Contrôle Permanent",
    "Contrôle Permanent Groupe",
    "PASS",
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model("kyc", "KycMatchValidatorRole")
    for organe in DEFAULT_VALIDATOR_ORGANES:
        Role.objects.get_or_create(organe=organe, defaults={"can_validate": True, "can_reject": True})


def unseed_roles(apps, schema_editor):
    Role = apps.get_model("kyc", "KycMatchValidatorRole")
    Role.objects.filter(organe__in=DEFAULT_VALIDATOR_ORGANES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0049_kycmatchvalidatorrole_kycmatchdecision'),
    ]

    operations = [
        migrations.RunPython(seed_roles, unseed_roles),
    ]
