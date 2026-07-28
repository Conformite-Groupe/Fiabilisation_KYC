from django.db import migrations


def sync_sidebar_access_with_profile_organs(apps, schema_editor):
    ProfileV = apps.get_model('accounts', 'ProfileV')
    SidebarAccess = apps.get_model('kyc', 'SidebarAccess')
    perm_fields = [
        "dashboard", "agents_notes", "champs_non_renseignes", "clients_anomalie",
        "scoring_clients", "screening_kyc", "nouvelle_notation", "historique_notation",
        "ppe", "comptes_specifiques", "parametrage_utilisateurs", "regles_qualite",
        "champs_kyc", "documents_screening", "rappels_scoring", "pilotage", "audit",
    ]

    legacy_defaults = {
        "PASS": {field: True for field in perm_fields},
        "DSI": {
            "dashboard": True, "agents_notes": True, "champs_non_renseignes": True,
            "clients_anomalie": True, "scoring_clients": True, "screening_kyc": True,
            "parametrage_utilisateurs": True, "pilotage": True, "audit": True,
        },
    }

    def mojibake(value):
        try:
            return value.encode("utf-8").decode("cp1252")
        except UnicodeError:
            return value

    for organe in ProfileV.objects.exclude(organe="").values_list("organe", flat=True).distinct():
        source = SidebarAccess.objects.filter(organe=organe).first()
        if source is None:
            source = SidebarAccess.objects.filter(organe=mojibake(organe)).first()

        if source is not None:
            defaults = {field: getattr(source, field) for field in perm_fields}
        else:
            defaults = {field: False for field in perm_fields}
            defaults.update(legacy_defaults.get(organe, {}))
            defaults["dashboard"] = True
            defaults["champs_non_renseignes"] = True
            defaults["clients_anomalie"] = True
            defaults["scoring_clients"] = True
            defaults["screening_kyc"] = True

        SidebarAccess.objects.update_or_create(organe=organe, defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('kyc', '0065_sidebaraccess'),
    ]

    operations = [
        migrations.RunPython(sync_sidebar_access_with_profile_organs, migrations.RunPython.noop),
    ]
