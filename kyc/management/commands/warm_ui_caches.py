import hashlib

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.test import RequestFactory
from django.utils import timezone

from kyc.models import (
    DataQualityRule, TauxEvolution_filiale, EmailReminderConfig, Kyc_pp, Kyc_pm, TauxQualite,
)
from kyc.views import (
    _evaluate_data_quality_rule_scoped,
    _quality_cache_version,
    _rule_eval_filiale,
    _get_exploitants_daterev_expired,
    evaluate_data_quality_rule,
    evaluate_data_quality_scope,
    devise,
    devise_pm,
    non_anom,
    non_resid,
    non_resid_pm,
    pilotage_kyc,
    ppe,
    statistiques,
    taux_evolution_view,
    taux_evolution_view_stock,
)


GROUP_ORGANS = {"PASS", "Conformité Groupe", "Contrôle Permanent Groupe", "GUEST"}
FILIALE_ORGANS = {"DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau", "Risques", "DAI", "Qualité"}


class Command(BaseCommand):
    help = "Prechauffe les caches des onglets lourds: quality_control, non_anom, statistiques, evolutions, PPE et comptes specifiques."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=20, help="Nombre maximum d'utilisateurs actifs a prechauffer.")
        parser.add_argument("--rules", type=int, default=0, help="Nombre de modales de regles /non_anom a prechauffer. 0 = aucune.")
        parser.add_argument("--quality-only", action="store_true", help="Ne prechauffe que les caches qualite/non_anom.")
        parser.add_argument("--dashboards-only", action="store_true", help="Ne prechauffe que les caches statistiques/evolutions.")
        parser.add_argument("--specific-only", action="store_true", help="Ne prechauffe que les pages PPE et comptes specifiques.")
        parser.add_argument("--skip-snapshot", action="store_true",
                            help="Ne recalcule pas la table TauxQualite (deja remplie par compute_quality_rates).")
        parser.add_argument("--slice", type=str, default="1/1", help="Decoupage parallele des utilisateurs, format i/N (ex. 2/6 = worker 2 sur 6). Chaque worker traite un sous-ensemble disjoint des utilisateurs.")

    def handle(self, *args, **options):
        max_users = max(options["users"], 0)
        max_rules = max(options["rules"], 0)
        quality_only = options["quality_only"]
        dashboards_only = options["dashboards_only"]
        specific_only = options["specific_only"]

                                                                                 
                                                                                    
                                                                          
        try:
            slice_idx, slice_total = (int(x) for x in options["slice"].split("/"))
        except (ValueError, AttributeError):
            slice_idx, slice_total = 1, 1
        if slice_total < 1 or not (1 <= slice_idx <= slice_total):
            slice_idx, slice_total = 1, 1

        users = self._representative_users(max_users)
        if slice_total > 1:
            users = users[slice_idx - 1::slice_total]
        if not users:
            self.stdout.write(self.style.WARNING("Aucun utilisateur actif pour ce slice."))
            return

        warmed = {"quality": 0, "non_anom": 0, "taux_qualite": 0, "dashboards": 0, "pilotage": 0, "specific": 0, "daterev": 0}

        if not dashboards_only and not specific_only:
                                                                                  
                                                                                
            warmed["quality"] = self._warm_quality_rule_stats(users, include_global=(slice_idx == 1))
            warmed["non_anom"] = self._warm_non_anom(users, max_rules)

        if not quality_only and not specific_only:
                                                                                
                                                                                 
                                                                                  
                                                                   
            if not options["skip_snapshot"]:
                warmed["taux_qualite"] = self._warm_quality_snapshot(users)
            warmed["dashboards"] = self._warm_dashboards(users)
            warmed["pilotage"] = self._warm_pilotage(users)

        if not quality_only and not dashboards_only:
            warmed["specific"] = self._warm_specific_accounts(users)

        warmed["daterev"] = self._warm_daterev_reminders()

        self.stdout.write(
            self.style.SUCCESS(
                "Prechauffage termine: "
                f"quality={warmed['quality']}, non_anom={warmed['non_anom']}, "
                f"taux_qualite={warmed['taux_qualite']}, dashboards={warmed['dashboards']}, "
                f"pilotage={warmed['pilotage']}, "
                f"specific={warmed['specific']}, daterev={warmed['daterev']}."
            )
        )

    def _representative_users(self, max_users):
        User = get_user_model()
        users = []
        seen_scopes = set()

        preferred = User.objects.filter(is_active=True).order_by("-is_superuser", "organe", "filiale", "agence", "code_expl")
        for user in preferred:
            scope = (
                user.organe or "",
                user.filiale or "",
                user.agence or "",
                user.code_expl or "",
            )
            if scope in seen_scopes:
                continue
            users.append(user)
            seen_scopes.add(scope)
            if max_users and len(users) >= max_users:
                break
        return users

    def _scope_for_user(self, user):
        organe = (getattr(user, "organe", "") or "").strip()
        if "Charg" in organe and "Client" in organe:
            return user.filiale or None, user.agence or None, user.code_expl or None
        if organe == "Directeur Agence":
            return user.filiale or None, user.agence or None, None
        if organe in FILIALE_ORGANS:
            return user.filiale or None, None, None
        if organe in GROUP_ORGANS:
            return None, None, None
        return user.filiale or None, None, None

    def _warm_quality_rule_stats(self, users, include_global=True):
        rules = list(DataQualityRule.objects.filter(active=True).prefetch_related("conditions"))
        rules_version = _quality_cache_version()
        data_refresh_bucket = timezone.localdate().isoformat()
        warmed = 0

                                                                                    
                                                                               
        for rule in rules if include_global else []:
            quality_signature = (
                f"{rule.id}|{rule.name}|{rule.applicability}|{rule.filiale}|"
                f"{rule.field_name}|{rule.control_type}|{rule.parameter}|{rule.active}"
            )
            quality_key = f"quality_control:stat:v{rules_version}:d{data_refresh_bucket}:{hashlib.md5(quality_signature.encode('utf-8')).hexdigest()}"
            if cache.get(quality_key) is None:
                cache.set(quality_key, _evaluate_data_quality_rule_scoped(rule), timeout=86400)
                warmed += 1

                                                                                         
                                                                                   
                                                                                   
        distinct_scopes = {self._scope_for_user(user) for user in users}
        for filiale, agence, expl in distinct_scopes:
            for rule in rules:
                rule_eval_filiale = _rule_eval_filiale(rule, filiale)
                non_anom_signature = (
                    f"{rule.id}|{rule.name}|{rule.applicability}|{rule.field_name}|"
                    f"{rule.control_type}|{rule.parameter}|{rule.filiale}|"
                    f"{rule_eval_filiale}|{agence}|{expl}"
                )
                non_anom_key = f"quality_control:non_anom:v{rules_version}:d{data_refresh_bucket}:{hashlib.md5(non_anom_signature.encode('utf-8')).hexdigest()}"
                if cache.get(non_anom_key) is None:
                    stat = _evaluate_data_quality_rule_scoped(rule, filiale=rule_eval_filiale, agence=agence, expl=expl)
                    cache.set(non_anom_key, stat, timeout=86400)
                    warmed += 1

        return warmed

    def _warm_non_anom(self, users, max_rules):
        request_factory = RequestFactory()
        rules = list(DataQualityRule.objects.filter(active=True).order_by("applicability", "name")[:max_rules])
        warmed = 0

        for user in users:
            requests = [request_factory.get("/non_anom/")]
            for rule in rules:
                requests.append(request_factory.get(f"/non_anom/?rule={rule.pk}"))
            for request in requests:
                request.user = user
                non_anom(request)
                warmed += 1

        return warmed

    def _warm_quality_snapshot(self, users):
        """Precalcule la table TauxQualite pour les scopes de CE slice d'utilisateurs.

        Reproduit a l'identique compute_quality_rate_by_typology (kyc/views.py) :
        somme(ok_count)/somme(total) sur toutes les regles actives du scope.
        statistiques() lira ce snapshot au lieu de rescanner Kyc_pp. Le scope est
        derive via evaluate_data_quality_scope -> meme cle que la lecture dashboard.
        """
        today = timezone.localdate()
        seen = set()
        written = 0
        for user in users:
            scope = evaluate_data_quality_scope(user)
            key = (scope.get("filiale"), scope.get("agence"), scope.get("expl"))
            if key in seen:
                continue
            seen.add(key)
            filiale, agence, expl = key
            for applicability in ("PP", "PM"):
                rules = list(DataQualityRule.objects.filter(active=True, applicability=applicability))
                total_ok = 0
                total_evaluated = 0
                for rule in rules:
                    stat = evaluate_data_quality_rule(rule, filiale=filiale, agence=agence, expl=expl)
                    total_ok += stat.get("ok_count", 0)
                    total_evaluated += stat.get("total", 0)
                rate = round(total_ok / total_evaluated * 100, 1) if total_evaluated else 0
                TauxQualite.objects.update_or_create(
                    filiale=filiale, agence=agence, expl=expl,
                    applicability=applicability, flux_stock="stock", date=today,
                    defaults={"rate": rate, "ok_count": total_ok, "total": total_evaluated},
                )
                written += 1
        return written

    def _warm_dashboards(self, users):
        request_factory = RequestFactory()
                                                                                
                                                                             
                                                                              
        periods = ["journalier", "hebdomadaire", "mensuel", "annuel"]
        warmed = 0

        def _hit(user, path, view_func):
            nonlocal warmed
            request = request_factory.get(path)
            request.user = user
            view_func(request)
            warmed += 1

        for user in users:
            _hit(user, "/statistiques/", statistiques)
            for mode in ["Flux", "Stock"]:
                for periode in periods:
                    _hit(user, f"/statistiques/?mode={mode}&periode={periode}", statistiques)

            _hit(user, "/evolution_filiale/", taux_evolution_view)
            _hit(user, "/evolution_filiale_stock/", taux_evolution_view_stock)
            for periode in periods:
                _hit(user, f"/evolution_filiale/?periode={periode}", taux_evolution_view)
                _hit(user, f"/evolution_filiale_stock/?periode={periode}", taux_evolution_view_stock)

            if getattr(user, "organe", "") in GROUP_ORGANS:
                for filiale in TauxEvolution_filiale.objects.values_list("filiale", flat=True).distinct()[:10]:
                    _hit(user, f"/evolution_filiale/?filiale={filiale}&periode=mensuel", taux_evolution_view)
                    _hit(user, f"/evolution_filiale_stock/?filiale={filiale}&periode=mensuel", taux_evolution_view_stock)

        return warmed

    def _warm_pilotage(self, users):
        """Prechauffe /pilotage-kyc : la partie lourde (completude + qualite sur
        Kyc_pp/Kyc_pm) est INDEPENDANTE DU SEUIL et mise en cache journalier par
        _pilotage_base_payload. On force le recalcul (_force_daily_cache_refresh)
        pour un scope groupe (habilites) et un scope filiale par filiale, de sorte
        que le chargement au seuil par defaut soit ensuite quasi instantane."""
        request_factory = RequestFactory()
        pilotage_group_organs = {
            "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
            "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST",
        }
        pilotage_filiale_organs = {"Conformité", "DSI", "Qualité", "Contrôle Permanent"}
        warmed = 0
        seen_paths = set()

        for user in users:
            organe = (getattr(user, "organe", "") or "").strip()
            can_group = bool(getattr(user, "is_superuser", False)) or organe in pilotage_group_organs
            if not (can_group or organe in pilotage_filiale_organs):
                continue

            paths = []
            if can_group:
                                                                                  
                paths.append("/pilotage-kyc/?scope=groupe")
                paths.append("/pilotage-kyc/?scope=filiale")
            else:
                fil = (getattr(user, "filiale", "") or "").strip()
                paths.append(f"/pilotage-kyc/?scope=filiale&filiale={fil}")

            for path in paths:
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                request = request_factory.get(path)
                request.user = user
                request._force_daily_cache_refresh = True
                try:
                    pilotage_kyc(request)
                    warmed += 1
                except Exception as exc:                                                           
                    self.stdout.write(self.style.WARNING(f"pilotage {path}: {exc}"))

        return warmed

    def _warm_daterev_reminders(self):
        import hashlib
        from django.utils import timezone
        config = EmailReminderConfig.objects.filter(active=True).order_by('-updated_at').first()
        days_before = config.days_before if config else 30
        today = timezone.localdate().isoformat()

        def _drev_key(fil):
            slug = hashlib.md5((fil or 'all').encode()).hexdigest()[:12]
            return f"drevpaid:{slug}:{today}:{days_before}"

        global_key = _drev_key(None)
        if cache.get(global_key) is None:
            cache.set(global_key, _get_exploitants_daterev_expired(None, days_before, only_paid=True), timeout=3600)

                                                                         
        from kyc.views import _paid_daterev_filiales
        filiales = sorted(_paid_daterev_filiales())
        warmed = 1
        for filiale in filiales:
            fkey = _drev_key(filiale)
            if cache.get(fkey) is None:
                cache.set(fkey, _get_exploitants_daterev_expired(filiale, days_before, only_paid=True), timeout=3600)
                warmed += 1

        return warmed

    def _warm_specific_accounts(self, users):
        request_factory = RequestFactory()
        views = [
            ("/ppe/", ppe),
            ("/devise/", devise),
            ("/devise_pm/", devise_pm),
            ("/non_resid/", non_resid),
            ("/non_resid_pm/", non_resid_pm),
        ]
        warmed = 0

        for user in users:
            for path, view_func in views:
                request = request_factory.get(path)
                request.user = user
                request._force_daily_cache_refresh = True
                view_func(request)
                warmed += 1

        return warmed
