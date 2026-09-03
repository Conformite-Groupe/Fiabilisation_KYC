import os, json, django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from django.db import transaction
from django.contrib.auth import get_user_model
from kyc.models import TauxEvolution, TauxEvolution_filiale, Notation, Devise

User = get_user_model()

with open("data_prod.json", encoding="utf-8") as fh:
    export = json.load(fh)

with transaction.atomic():
    TauxEvolution.objects.all().delete()
    TauxEvolution_filiale.objects.all().delete()
    Devise.objects.all().delete()
    Notation.objects.all().delete()

    TauxEvolution.objects.bulk_create(
        [TauxEvolution(**d) for d in export["taux_evolution"]], batch_size=500
    )
    TauxEvolution_filiale.objects.bulk_create(
        [TauxEvolution_filiale(**d) for d in export["taux_evolution_filiale"]], batch_size=500
    )
    Devise.objects.bulk_create([Devise(**d) for d in export["devise"]])

    index = {}
    for u in User.objects.all():
        for cle in (u.username, u.email, u.code_expl):
            if cle:
                index.setdefault(str(cle).strip().lower(), u)

    def retrouver(ident):
        for cle in (ident.get("username"), ident.get("email"), ident.get("expl")):
            if cle:
                u = index.get(str(cle).strip().lower())
                if u:
                    return u
        return None

    notations, ignorees = [], []
    for d in export["notation"]:
        agent = retrouver(d.pop("agent_ident"))
        note_par = retrouver(d.pop("note_par_ident"))
        if agent is None or note_par is None:
            ignorees.append(d)
            continue
        notations.append(Notation(agent=agent, note_par=note_par, **d))
    Notation.objects.bulk_create(notations, batch_size=500)

print(f"TauxEvolution: {TauxEvolution.objects.count()}")
print(f"TauxEvolution_filiale: {TauxEvolution_filiale.objects.count()}")
print(f"Devise: {Devise.objects.count()}")
print(f"Notation: {len(notations)} importées, {len(ignorees)} ignorées (utilisateur absent en test)")