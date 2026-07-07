"""
Crée les règles de contrôle qualité KYC (modèle DataQualityRule + DataQualityCondition)
pour les filiales BOA SN et BOA RDC, d'après le fichier Règles_Qualité_KYC.xlsx.

Idempotent : chaque règle est identifiée par (name, filiale). À chaque exécution la
règle est mise à jour et ses conditions sont réécrites (pas de doublons).

    python manage.py seed_quality_rules_boa            # crée / met à jour
    python manage.py seed_quality_rules_boa --deactivate-others
                                                       # désactive les autres règles
                                                       # portant sur ces filiales

Notes d'implémentation (moteur d'évaluation kyc/views.py) :
  * Une règle "composite" est en ANOMALIE lorsque TOUTES ses conditions matchent (ET).
    -> impossible d'exprimer "min ET max" sur un même champ (jamais <8 ET >15) :
       les contrôles de plage sont donc scindés en deux règles (trop court / trop long).
  * min_length matche si len(val) < seuil ; max_length matche si len(val) > seuil.
    Un garde-fou is_not_empty est ajouté pour ne pas confondre "manquant" et "invalide".
  * RISQUE en base = 'Risque eleve' / 'Risque moyen eleve' / ... -> "risque élevé"
    est encodé RISQUE = 'Risque eleve'.
  * PPE / RESID valent 'O' / 'N' ; non-résident = RESID = 'N'.
  * PROFESSION est en MAJUSCULES sans accent : 'salarié' est approché par contains EMPLOYE,
    'retraité' par contains RETRAIT, 'mineur/élève' par contains ELEVE.

Les seuils min/max (téléphone, RCS, NUMID, salaire élevé) sont des valeurs par défaut
raisonnables, ajustables ensuite depuis l'écran "Règles de Qualité".
"""
from django.core.management.base import BaseCommand
from django.db import transaction


FILIALE = "|BOA SN|BOA RDC|"

# Chaque règle : (name, applicability, field_name, description, [ (field, operator, value), ... ])
RULES = [
    # ─────────────────────────  ENTREPRISES (PM)  ─────────────────────────
    ("Format téléphone invalide (trop court)", "PM", "TEL",
     "Le numéro de téléphone renseigné comporte moins de 9 caractères.",
     [("TEL", "is_not_empty", ""), ("TEL", "min_length", "9")]),

    ("Format téléphone invalide (trop long)", "PM", "TEL",
     "Le numéro de téléphone renseigné dépasse 18 caractères.",
     [("TEL", "max_length", "18")]),

    ("Capital social nul", "PM", "CAPITAL",
     "Le capital social déclaré est égal à 0.",
     [("CAPITAL", "=", "0")]),

    ("Numéro RCS trop court", "PM", "RCSNO",
     "Le numéro RCS renseigné comporte moins de 6 caractères.",
     [("RCSNO", "is_not_empty", ""), ("RCSNO", "min_length", "6")]),

    ("PPE déclarée sans risque élevé", "PM", "PPE",
     "Client marqué PPE (PPE=O) mais dont la classe de risque n'est pas 'Risque eleve'.",
     [("PPE", "=", "O"), ("RISQUE", "!=", "Risque eleve")]),

    ("Société avec capital mais sans actionnaire", "PM", "CAPITAL",
     "Capital social > 0 alors qu'aucun actionnaire n'est renseigné.",
     [("CAPITAL", ">", "0"), ("ACTIONNAIRE", "is_empty", "")]),

    ("Résultat renseigné sans chiffre d'affaires", "PM", "RESULTAT",
     "Le résultat est renseigné mais le chiffre d'affaires (CA) est vide.",
     [("RESULTAT", "is_not_empty", ""), ("CA", "is_empty", "")]),

    ("RCS renseigné mais sans numéro fiscal", "PM", "RCSNO",
     "Numéro RCS présent mais numéro fiscal absent.",
     [("RCSNO", "is_not_empty", ""), ("NUMERO_FISCAL", "is_empty", "")]),

    ("CA positif mais résultat vide", "PM", "CA",
     "Chiffre d'affaires > 0 alors que le résultat n'est pas renseigné.",
     [("CA", ">", "0"), ("RESULTAT", "is_empty", "")]),

    ("Risque élevé sans révision KYC à jour", "PM", "RISQUE",
     "Client à risque élevé dont la date de révision (DATEREV) est dépassée.",
     [("RISQUE", "=", "Risque eleve"), ("DATEREV", "expired", "")]),

    ("Mandataire absent pour société active", "PM", "MANDATAIRE",
     "Société avec chiffre d'affaires > 0 mais sans mandataire renseigné.",
     [("CA", ">", "0"), ("MANDATAIRE", "is_empty", "")]),

    ("Client sans domaine d'activité (CODAPE)", "PM", "CODAPE",
     "Le code d'activité économique (CODAPE) n'est pas renseigné.",
     [("CODAPE", "is_empty", "")]),

    # ─────────────────────────  PARTICULIERS (PP)  ────────────────────────
    ("Format téléphone invalide (trop court)", "PP", "TEL",
     "Le numéro de téléphone renseigné comporte moins de 9 caractères.",
     [("TEL", "is_not_empty", ""), ("TEL", "min_length", "9")]),

    ("Format téléphone invalide (trop long)", "PP", "TEL",
     "Le numéro de téléphone renseigné dépasse 18 caractères.",
     [("TEL", "max_length", "18")]),

    ("Âge client supérieur à 100 ans (aberrant)", "PP", "DATNAIS",
     "La date de naissance implique un âge supérieur à 100 ans.",
     [("DATNAIS", "age_gt", "100")]),

    ("Pièce d'identité expirée", "PP", "DATVALID",
     "La date de validité de la pièce d'identité est dépassée.",
     [("DATVALID", "expired", "")]),

    ("Date de révision KYC expirée", "PP", "DATEREV",
     "La date de révision KYC (DATEREV) est dépassée.",
     [("DATEREV", "expired", "")]),

    ("NUMID trop court", "PP", "NUMID",
     "Le numéro de pièce d'identité comporte moins de 5 caractères.",
     [("NUMID", "is_not_empty", ""), ("NUMID", "min_length", "5")]),

    ("NUMID trop long", "PP", "NUMID",
     "Le numéro de pièce d'identité dépasse 18 caractères.",
     [("NUMID", "max_length", "18")]),

    ("PPE déclaré sans risque élevé", "PP", "PPE",
     "Client marqué PPE (PPE=O) mais dont la classe de risque n'est pas 'Risque eleve'.",
     [("PPE", "=", "O"), ("RISQUE", "!=", "Risque eleve")]),

    ("Salarié sans employeur", "PP", "PROFESSION",
     "Profession de type salarié (EMPLOYE) mais employeur non renseigné.",
     [("PROFESSION", "contains", "EMPLOYE"), ("EMPLOYEUR", "is_empty", "")]),

    ("Salarié sans revenu", "PP", "PROFESSION",
     "Profession de type salarié (EMPLOYE) mais salaire non renseigné.",
     [("PROFESSION", "contains", "EMPLOYE"), ("SALAIRE", "is_empty", "")]),

    ("Retraité avec revenu positif", "PP", "PROFESSION",
     "Profession de type retraité (RETRAIT) avec un salaire numérique > 0.",
     [("PROFESSION", "contains", "RETRAIT"), ("SALAIRE", ">", "0")]),

    ("Risque élevé sans révision KYC à jour", "PP", "RISQUE",
     "Client à risque élevé dont la date de révision (DATEREV) est dépassée.",
     [("RISQUE", "=", "Risque eleve"), ("DATEREV", "expired", "")]),

    ("PPE sans origine des revenus", "PP", "PPE",
     "Client PPE (PPE=O) sans origine des revenus renseignée.",
     [("PPE", "=", "O"), ("ORIGINE_REV", "is_empty", "")]),

    ("Non-résident sans boîte postale", "PP", "RESID",
     "Client non-résident (RESID=N) sans boîte postale renseignée.",
     [("RESID", "=", "N"), ("BOITE_POSTALE", "is_empty", "")]),

    ("Mineur / élève de plus de 21 ans", "PP", "PROFESSION",
     "Profession de type élève/mineur (ELEVE) avec un âge supérieur à 21 ans.",
     [("PROFESSION", "contains", "ELEVE"), ("DATNAIS", "age_gt", "21")]),

    ("Revenus élevés sans origine déclarée", "PP", "SALAIRE",
     "Salaire numérique supérieur à 50 000 000 sans origine des revenus renseignée.",
     [("SALAIRE", ">", "50000000"), ("ORIGINE_REV", "is_empty", "")]),
]


class Command(BaseCommand):
    help = "Crée les règles de contrôle qualité KYC pour BOA SN et BOA RDC (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--deactivate-others", action="store_true",
            help="Désactive les autres règles ciblant BOA SN / BOA RDC non gérées par ce seed.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from kyc.models import DataQualityRule, DataQualityCondition

        managed_keys = set()
        created = updated = 0

        for name, applicability, field_name, description, conditions in RULES:
            managed_keys.add((name, applicability))
            # Clé = (name, applicability, filiale) : PP et PM peuvent porter le même nom
            # (les badges dédiés distinguent le type dans l'UI).
            rule, is_created = DataQualityRule.objects.update_or_create(
                name=name, applicability=applicability, filiale=FILIALE,
                defaults={
                    "field_name": field_name,
                    "control_type": "composite",
                    "parameter": "",
                    "description": description,
                    "active": True,
                },
            )
            # Réécriture des conditions (évite les doublons entre exécutions)
            rule.conditions.all().delete()
            DataQualityCondition.objects.bulk_create([
                DataQualityCondition(rule=rule, field_name=f, operator=op, value=val)
                for (f, op, val) in conditions
            ])
            created += int(is_created)
            updated += int(not is_created)
            self.stdout.write(f"  [{'NEW' if is_created else 'UPD'}] {name}")

        if options["deactivate_others"]:
            others = [
                r for r in DataQualityRule.objects.filter(filiale=FILIALE, active=True)
                if (r.name, r.applicability) not in managed_keys
            ]
            n = DataQualityRule.objects.filter(id__in=[r.id for r in others]).update(active=False)
            self.stdout.write(self.style.WARNING(
                f"{n} autre(s) règle(s) BOA SN/RDC désactivée(s)."))

        self.stdout.write(self.style.SUCCESS(
            f"Terminé : {created} créée(s), {updated} mise(s) à jour "
            f"pour filiales {FILIALE.strip('|').replace('|', ' + ')}."))
