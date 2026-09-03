import os, json, django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from accounts.models import ProfileV
from django.contrib.auth.models import Group
from django.db import transaction

with open("profils_prod.json", encoding="utf-8") as fh:
    users = json.load(fh)

crees, maj = 0, 0
with transaction.atomic():
    for data in users:
        groupes = data.pop("groups", [])
        username = data.pop("username")
        obj, created = ProfileV.objects.update_or_create(
            username=username, defaults=data
        )
        obj.groups.set([Group.objects.get_or_create(name=n)[0] for n in groupes])
        crees += created
        maj += not created

print(f"{crees} utilisateurs créés, {maj} mis à jour")