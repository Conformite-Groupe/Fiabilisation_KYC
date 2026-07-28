                                                                              
                                                                         

from django.db import migrations

FULL_ACCESS_ORGANES = ["DSI", "PASS"]
CONSULT_ORGANES = [
    "Conformité",
    "Conformité Groupe",
    "Contrôle Permanent",
    "Contrôle Permanent Groupe",
]


def seed_access(apps, schema_editor):
    Access = apps.get_model("kyc", "KycScreeningAccess")
    for organe in FULL_ACCESS_ORGANES:
        Access.objects.get_or_create(organe=organe, defaults={
            "tab_charger": True, "tab_suivi": True, "tab_resultats": True,
            "tab_sources": True, "tab_documents": True,
            "can_upload_batches": True, "can_run_matching": True,
        })
    for organe in CONSULT_ORGANES:
        Access.objects.get_or_create(organe=organe, defaults={
            "tab_charger": False, "tab_suivi": False, "tab_resultats": True,
            "tab_sources": False, "tab_documents": True,
            "can_upload_batches": False, "can_run_matching": False,
        })


def unseed_access(apps, schema_editor):
    Access = apps.get_model("kyc", "KycScreeningAccess")
    Access.objects.filter(organe__in=FULL_ACCESS_ORGANES + CONSULT_ORGANES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("kyc", "0057_kycscreeningaccess"),
    ]

    operations = [
        migrations.RunPython(seed_access, unseed_access),
    ]
