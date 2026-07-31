# -*- coding: utf-8 -*-
"""Génère le rapport d'audit KYC d'une filiale, en une commande.

    python generate_report.py --filiale SN
    python generate_report.py --filiale CI --dossier D:/exports --json

Entrées attendues dans le dossier de travail :
    pp_XX_STOCK.csv          export particuliers  (produit par Script_V3.r)
    pm_XX_STOCK.csv          export entreprises   (produit par Script_V3.r)
    quality_rules_export.json référentiel des règles qualité de la plateforme
    assets_tpl/tpl_image1.png logo repris du modèle (facultatif)

Sortie :
    Audit_KYC_BOA_XX_AAAAMMJJ.pptx  (+ .json avec --json)
"""
import argparse
import json
import os
import sys
from datetime import date


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Audit KYC : complétude, qualité, segments sensibles, scoring AML.")
    p.add_argument("--filiale", "-f", required=True,
                   help="Code ISO 2 de la filiale (SN, CI, BJ, ML, BF, ...)")
    p.add_argument("--dossier", "-d", default=".",
                   help="Dossier contenant les exports (défaut : dossier courant)")
    p.add_argument("--sortie", "-o", default=None,
                   help="Chemin du PPTX (défaut : Audit_KYC_BOA_XX_AAAAMMJJ.pptx)")
    p.add_argument("--regles", default=None,
                   help="Chemin du référentiel de règles (défaut : quality_rules_export.json)")
    p.add_argument("--date", default=None,
                   help="Date de référence AAAA-MM-JJ (défaut : aujourd'hui). "
                        "Pilote les opérateurs expired / age_gt.")
    p.add_argument("--json", action="store_true",
                   help="Écrire également les résultats bruts en JSON")
    args = p.parse_args(argv)

    sys.stdout.reconfigure(encoding="utf-8")
    from kyc_audit import deck, pipeline

    jour = date.fromisoformat(args.date) if args.date else date.today()
    iso = args.filiale.strip().upper()

    print(f"=== Audit KYC BOA {iso} — référence {jour.isoformat()} ===")
    R = pipeline.executer(iso, dossier=args.dossier, regles_path=args.regles, today=jour)

    sortie = args.sortie or os.path.join(
        args.dossier, f"Audit_KYC_BOA_{iso}_{jour.strftime('%Y%m%d')}.pptx")
    chemin, n = deck.construire(R, sortie)

    if args.json:
        cj = os.path.splitext(chemin)[0] + ".json"
        with open(cj, "w", encoding="utf-8") as f:
            json.dump(R, f, ensure_ascii=False, indent=1)
        print(f"  résultats bruts : {cj}")

    c, q = R["completude"], R["qualite"]
    print(f"  PP : {R['source']['pp']['lignes']:>8} lignes | complétude "
          f"{c['pp']['taux_global']} % | qualité {q['pp']['taux_qualite']} %")
    print(f"  PM : {R['source']['pm']['lignes']:>8} lignes | complétude "
          f"{c['pm']['taux_global']} % | qualité {q['pm']['taux_qualite']} %")
    print(f"=== {n} diapositives -> {chemin} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
