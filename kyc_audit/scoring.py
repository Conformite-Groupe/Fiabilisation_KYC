# -*- coding: utf-8 -*-
"""Revue Scoring AML : cartographie du champ RISQUE et échéances DATREV."""
from collections import Counter, defaultdict

from .config import ECHEANCES, ECHEANCE_LOINTAINE, RETARDS, RETARD_LOINTAIN
from .dataset import parse_date

NIVEAUX = ["Risque faible", "Risque moyen faible", "Risque moyen eleve",
           "Risque eleve", "(non renseigné)"]
NIVEAUX_LIB = {"Risque faible": "Faible",
               "Risque moyen faible": "Moyen faible",
               "Risque moyen eleve": "Moyen élevé",
               "Risque eleve": "Élevé",
               "(non renseigné)": "Non noté"}

STATUTS = ["Échue", "Non renseignée", "À échoir < 3 mois", "À échoir 3–6 mois",
           "À échoir 6–12 mois", "À échoir > 12 mois", "Format invalide"]

SANS_REVISION = ("Échue", "Non renseignée", "Format invalide")


def statut_daterev(brut, today):
    d = parse_date(brut)
    if not (brut or "").strip():
        return "Non renseignée", None
    if d is None:
        return "Format invalide", None
    if d < today:
        return "Échue", (today - d).days
    ecart = (d - today).days
    for seuil, libelle in ECHEANCES:
        if ecart <= seuil:
            return libelle, ecart
    return ECHEANCE_LOINTAINE, ecart


def _retard(jours):
    for seuil, libelle in RETARDS:
        if jours <= seuil:
            return libelle
    return RETARD_LOINTAIN


def analyser(t, today):
    n = len(t)
    ir, idr = t.col("RISQUE"), t.col("DATREV")

    risque = Counter()
    statuts = Counter()
    croise = defaultdict(Counter)
    anciennete = Counter()

    for r in t.rows:
        niveau = (r[ir] if ir is not None else "") or "(non renseigné)"
        if niveau not in NIVEAUX:
            niveau = niveau if niveau in NIVEAUX else (
                niveau if niveau.startswith("Risque") else "(hors référentiel)")
        risque[niveau] += 1

        st, jours = statut_daterev(r[idr] if idr is not None else "", today)
        statuts[st] += 1
        croise[niveau][st] += 1
        if st == "Échue":
            anciennete[_retard(jours)] += 1

    sans_rev = sum(statuts.get(s, 0) for s in SANS_REVISION)

    eleve = croise.get("Risque eleve", Counter())
    eleve_total = sum(eleve.values())
    eleve_ko = sum(eleve.get(s, 0) for s in SANS_REVISION)

    return {
        "n": n,
        "risque": dict(risque),
        "risque_ordonne": [(niv, risque.get(niv, 0)) for niv in NIVEAUX
                           if risque.get(niv, 0)],
        "risque_non_renseigne": risque.get("(non renseigné)", 0),
        "statuts": dict(statuts),
        "statuts_ordonnes": [(s, statuts.get(s, 0)) for s in STATUTS
                             if statuts.get(s, 0)],
        "sans_revision": sans_rev,
        "part_sans_revision": round(sans_rev / n * 100, 1) if n else 0.0,
        "anciennete_echues": dict(anciennete),
        "croise": {k: dict(v) for k, v in croise.items()},
        "risque_eleve": {
            "total": eleve_total,
            "sans_revision": eleve_ko,
            "part": round(eleve_ko / eleve_total * 100, 1) if eleve_total else 0.0,
            "echue": eleve.get("Échue", 0),
            "non_renseignee": eleve.get("Non renseignée", 0),
        },
    }


def coherence_ppe(t):
    """PPE déclarés et cohérence avec le niveau de risque."""
    if not t.a_colonne("PPE"):
        return {"disponible": False}
    ir = t.col("RISQUE")
    ppe = [r for r in t.rows if t.est_ppe(r)]
    sans_eleve = sum(1 for r in ppe if (r[ir] if ir is not None else "") != "Risque eleve")
    return {
        "disponible": True,
        "ppe": len(ppe),
        "part": round(len(ppe) / len(t) * 100, 2) if len(t) else 0.0,
        "sans_risque_eleve": sans_eleve,
        "avec_risque_eleve": len(ppe) - sans_eleve,
    }
