"""
Calcule et stocke l'appréciation globale par agent (filiale + exploitant)
selon la matrice du script R `appreciation_globale.r`.

À planifier (cron / tâche planifiée), p.ex. chaque nuit :
    python manage.py compute_appreciation_globale
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Max

from kyc.models import (
    Appreciation_globale, AppreciationConfig, DataQualityRule,
    Notation, TauxEvolution,
)
from kyc.appreciation import (
    appreciation_qualite, appreciation_globale, mesure_from_appreciation,
    current_trimestre,
)


class Command(BaseCommand):
    help = "Calcule l'appréciation globale de chaque agent (matrice appreciation_globale.r)."

    def add_arguments(self, parser):
        parser.add_argument("--filiale", type=str, default=None,
                            help="Limiter à une filiale donnée.")
        parser.add_argument("--verbose", action="store_true", help="Affiche le détail par agent.")

    def handle(self, *args, **options):
        from accounts.models import ProfileV  # import tardif (évite les cycles)

        # Trimestre courant par filiale (une config unique par filiale)
        trimestre_par_filiale = {}
        for cfg in AppreciationConfig.objects.filter(active=True).exclude(filiale=""):
            trimestre_par_filiale[cfg.filiale.strip().upper()] = current_trimestre(cfg.date_demarrage)
        if trimestre_par_filiale:
            apercu = ", ".join(f"{f}=T{t}" for f, t in sorted(trimestre_par_filiale.items()))
            self.stdout.write(f"Trimestres par filiale : {apercu}")
        else:
            self.stdout.write("Aucune configuration par filiale — trimestre 1 par défaut.")

        def trimestre_for(fil):
            return trimestre_par_filiale.get((fil or "").strip().upper(), 1)

        filiale_filter = options.get("filiale")

        # ── 1. Univers des agents : (filiale, expl) présents dans TauxEvolution flux ──
        evo_qs = TauxEvolution.objects.filter(flux_stock="F").exclude(expl="")
        if filiale_filter:
            evo_qs = evo_qs.filter(filiale=filiale_filter)
        agents = set(evo_qs.values_list("filiale", "expl").distinct())

        if not agents:
            self.stdout.write(self.style.WARNING("Aucun agent (TauxEvolution flux) trouvé."))
            return

        # ── 2. Taux d'évolution flux (moyenne PP + PM, dernier point) ──
        def taux_evolution_agent(fil, expl):
            vals = []
            for pp in ("P", "M"):
                rec = (TauxEvolution.objects
                       .filter(filiale=fil, expl=expl, flux_stock="F", pp_pm=pp)
                       .order_by("-date").first())
                if rec and rec.taux is not None:
                    vals.append(rec.taux)
            return round(sum(vals) / len(vals), 1) if vals else None

        # ── 3. Notation flux la plus récente par agent (filiale, code_expl) ──
        notes = Notation.objects.filter(flux_stock="Flux")
        latest = notes.values("agent").annotate(d=Max("date_notation"))
        latest_dates = {n["agent"]: n["d"] for n in latest}
        notation_by_agentid = {}
        for n in notes.filter(date_notation__in=latest_dates.values()).select_related("agent"):
            if latest_dates.get(n.agent_id) == n.date_notation:
                notation_by_agentid[n.agent_id] = n.note
        # index (filiale_upper, code_expl_upper) -> (ProfileV, note)
        profile_idx = {}
        for p in ProfileV.objects.exclude(code_expl="").exclude(code_expl__isnull=True):
            key = ((p.filiale or "").strip().upper(), (p.code_expl or "").strip().upper())
            profile_idx[key] = p

        # ── 4. Taux de qualité par agent (conformité des règles, scopé filiale+expl) ──
        from kyc.views import evaluate_data_quality_rule
        rules = list(DataQualityRule.objects.filter(active=True))

        def taux_qualite_agent(fil, expl):
            ok = tot = 0
            for rule in rules:
                stat = evaluate_data_quality_rule(rule, filiale=fil, expl=expl)
                tot += stat.get("total", 0)
                ok += stat.get("ok_count", 0)
            if tot == 0:
                # Aucune donnée qualité pour cet agent -> taux par défaut 100 %
                return 100.0
            # Arrondi à l'entier inférieur (floor) pour ne pas surévaluer / rater de client
            import math
            rate = math.floor(100.0 * ok / tot)
            # La moindre non-conformité (même infime) plafonne à 99 % : seul un
            # agent parfait (0 anomalie) atteint 100 %.
            if ok < tot:
                rate = min(rate, 99)
            return float(rate)

        # ── 5. Calcul + stockage ──
        created = updated = 0
        for fil, expl in sorted(agents):
            trimestre = trimestre_for(fil)
            te = taux_evolution_agent(fil, expl)
            tq = taux_qualite_agent(fil, expl)
            prof = profile_idx.get((fil.strip().upper(), expl.strip().upper()))
            note = notation_by_agentid.get(prof.id, "") if prof else ""

            appr_q = appreciation_qualite(tq, note)
            appr_g = appreciation_globale(te, appr_q, trimestre)
            mesure = mesure_from_appreciation(appr_g)

            obj, is_created = Appreciation_globale.objects.update_or_create(
                filiale=fil, expl=expl,
                defaults={
                    "agent": prof,
                    "trimestre": trimestre,
                    "taux_evolution": te,
                    "taux_qualite": tq,
                    "notation": note or "",
                    "appreciation_qualite": appr_q,
                    "appreciation_globale": appr_g,
                    "mesure": mesure,
                },
            )
            created += int(is_created)
            updated += int(not is_created)
            if options.get("verbose"):
                self.stdout.write(f"  {fil} / {expl} (T{trimestre}): évo={te} qual={tq} "
                                  f"note={note or '—'} -> {appr_q} / {appr_g}")

        self.stdout.write(self.style.SUCCESS(
            f"Appréciation globale calculée : {created} créées, {updated} mises à jour "
            f"({created + updated} agents)."))
