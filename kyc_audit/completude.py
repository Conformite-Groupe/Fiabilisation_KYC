# -*- coding: utf-8 -*-
"""Complétude — réplique exacte de Script_V3.r.

    field_completion_rate(df, f) = floor(100 - (nb_vides / n) * 100)
    compute_taux(df, fields)     = floor(100 * (1 - vides / (nb_champs * n)))
    get_appreciation(taux, 80, 100) -> Faible / Moyen / Bon

« Vide » = chaîne vide après nettoyage des espaces (inc = c("")).
"""
import math
from collections import defaultdict

from .config import SEUIL_FAIBLE, SEUIL_MOYEN


def taux_champ(t, champ):
    n = len(t)
    i = t.col(champ)
    if n == 0 or i is None:
        return None
    vides = sum(1 for r in t.rows if not r[i])
    return math.floor(100 - (vides / n) * 100)


def vides_champ(t, champ):
    i = t.col(champ)
    return None if i is None else sum(1 for r in t.rows if not r[i])


def taux_global(t, champs):
    n = len(t)
    if n == 0:
        return None
    idx = [i for i in (t.col(c) for c in champs) if i is not None]
    if not idx:
        return None
    vides = sum(1 for r in t.rows for i in idx if not r[i])
    return math.floor(100 * (1 - vides / (len(idx) * n)))


def appreciation(taux, faible=SEUIL_FAIBLE, moyen=SEUIL_MOYEN):
    if taux is None:
        return "Aucune donnée"
    if taux < faible:
        return "Faible"
    if taux < moyen:
        return "Moyen"
    return "Bon"


def analyser(t, champs):
    n = len(t)
    idx = [(c, t.col(c)) for c in champs]
    complets = sum(1 for r in t.rows if all(r[i] for _, i in idx if i is not None))
    tg = taux_global(t, champs)
    return {
        "n": n,
        "taux_global": tg,
        "appreciation": appreciation(tg),
        "par_champ": {c: taux_champ(t, c) for c in champs},
        "vides_par_champ": {c: vides_champ(t, c) for c in champs},
        "champs_absents": [c for c, i in idx if i is None],
        "clients_complets": complets,
        "part_clients_complets": round(complets / n * 100, 1) if n else 0.0,
    }


def par_agence(t, champs, mini=0):
    """Taux de complétude agence par agence, trié du plus faible au plus élevé."""
    ia, il = t.col("AGENCE"), t.col("AGENCELIB")
    if ia is None:
        return []
    groupes = defaultdict(list)
    for r in t.rows:
        groupes[r[ia]].append(r)
    out = []
    for code, lignes in groupes.items():
        if len(lignes) < mini:
            continue
        out.append({
            "agence": code,
            "libelle": lignes[0][il] if il is not None else "",
            "n": len(lignes),
            "taux": taux_global(t.sous_table(lignes), champs),
        })
    out.sort(key=lambda x: (x["taux"] if x["taux"] is not None else -1, -x["n"]))
    return out
