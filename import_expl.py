import os, json, django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from django.db import transaction
from accounts.models import ProfileV

with open("codes_expl_prod.json", encoding="utf-8") as fh:
    lignes = json.load(fh)

maj, deja_ok, introuvables = 0, 0, []

index = {}
for p in ProfileV.objects.all():
    for cle in (p.username, p.email):
        if cle:
            index.setdefault(str(cle).strip().lower(), p)

with transaction.atomic():
    for l in lignes:
        profil = None
        for cle in (l.get("username"), l.get("email")):
            if cle:
                profil = index.get(str(cle).strip().lower())
                if profil:
                    break
        if profil is None:
            introuvables.append(l.get("username"))
            continue

        code_prod = l["code_expl"]
        if (profil.code_expl or "").strip() == code_prod:
            deja_ok += 1
            continue

        profil.code_expl = code_prod
        profil.save(update_fields=["code_expl"])
        maj += 1

print(f"{maj} profils de test mis à jour avec le code expl de prod")
print(f"{deja_ok} étaient déjà alignés")
if introuvables:
    print(f"{len(introuvables)} profils de prod absents en test : {introuvables[:20]}")