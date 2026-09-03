import os, json, django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

lignes = [
    {"username": p.username, "email": p.email, "code_expl": (p.code_expl or "").strip()}
    for p in User.objects.all()
]

with open("codes_expl_prod.json", "w", encoding="utf-8") as fh:
    json.dump(lignes, fh, ensure_ascii=False, indent=2)

avec_code = sum(1 for l in lignes if l["code_expl"])
print(f"{len(lignes)} profils exportés, dont {avec_code} avec un code expl")