import os, json, django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import TauxEvolution, TauxEvolution_filiale, Notation, Devise


def serialiser(obj, exclus=("id",)):
    data = {}
    for f in obj._meta.concrete_fields:
        if f.name in exclus:
            continue
        val = getattr(obj, f.name)
        if val is None or isinstance(val, (str, int, float, bool)):
            data[f.name] = val
        else:
            data[f.name] = str(val)
    return data


def ident_user(u):
    """Identifiants possibles de l'utilisateur (ancien modèle Agents ou nouveau ProfileV)."""
    return {
        "username": getattr(u, "username", None),
        "email": getattr(u, "email", None),
        "expl": getattr(u, "expl", None) or getattr(u, "code_expl", None),
    }


export = {
    "taux_evolution": [serialiser(o) for o in TauxEvolution.objects.all()],
    "taux_evolution_filiale": [serialiser(o) for o in TauxEvolution_filiale.objects.all()],
    "devise": [serialiser(o) for o in Devise.objects.all()],
    "notation": [],
}

for n in Notation.objects.select_related("agent", "note_par"):
    data = serialiser(n, exclus=("id", "agent", "note_par"))
    data["agent_ident"] = ident_user(n.agent)
    data["note_par_ident"] = ident_user(n.note_par)
    export["notation"].append(data)

with open("data_prod.json", "w", encoding="utf-8") as fh:
    json.dump(export, fh, ensure_ascii=False, indent=2)

for k, v in export.items():
    print(f"{k}: {len(v)} lignes exportées")