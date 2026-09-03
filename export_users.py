import os, json, django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from accounts.models import ProfileV

CHAMPS_EXCLUS = {"id"}

users = []
for u in ProfileV.objects.all():
    data = {}
    for f in ProfileV._meta.concrete_fields:
        if f.name in CHAMPS_EXCLUS:
            continue
        val = getattr(u, f.name)
        data[f.name] = str(val) if val is not None and not isinstance(val, (str, int, float, bool)) else val
    data["groups"] = list(u.groups.values_list("name", flat=True))
    users.append(data)

with open("profils_prod.json", "w", encoding="utf-8") as fh:
    json.dump(users, fh, ensure_ascii=False, indent=2)

print(f"{len(users)} utilisateurs exportés dans profils_prod.json")