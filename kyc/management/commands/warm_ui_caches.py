import hashlib

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.test import RequestFactory
from django.utils import timezone

from kyc.models import DataQualityRule, TauxEvolution_filiale
from kyc.views import (
    _evaluate_data_quality_rule_scoped,
    _quality_cache_version,
    _rule_eval_filiale,
    devise,
    devise_pm,
    non_anom,
    non_resid,
    non_resid_pm,
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

    def handle(self, *args, **options):
        max_users = max(options["users"], 0)
        max_rules = max(options["rules"], 0)
        quality_only = options["quality_only"]
        dashboards_only = options["dashboards_only"]
        specific_only = options["specific_only"]

        users = self._representative_users(max_users)
        if not users:
            self.stdout.write(self.style.WARNING("Aucun utilisateur actif trouve."))
            return

        warmed = {"quality": 0, "non_anom": 0, "dashboards": 0, "specific": 0}

        if not dashboards_only and not specific_only:
            warmed["quality"] = self._warm_quality_rule_stats(users)
            warmed["non_anom"] = self._warm_non_anom(users, max_rules)

        if not quality_only and not specific_only:
            warmed["dashboards"] = self._warm_dashboards(users)

        if not quality_only and not dashboards_only:
            warmed["specific"] = self._warm_specific_accounts(users)

        self.stdout.write(
            self.style.SUCCESS(
                "Prechauffage termine: "
                f"quality={warmed['quality']}, non_anom={warmed['non_anom']}, "
                f"dashboards={warmed['dashboards']}, specific={warmed['specific']}."
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

    def _warm_quality_rule_stats(self, users):
        rules = list(DataQualityRule.objects.filter(active=True).prefetch_related("conditions"))
        rules_version = _quality_cache_version()
        data_refresh_bucket = timezone.localdate().isoformat()
        warmed = 0

        for user in users:
            filiale, agence, expl = self._scope_for_user(user)
            for rule in rules:
                quality_signature = (
                    f"{rule.id}|{rule.name}|{rule.applicability}|{rule.filiale}|"
                    f"{rule.field_name}|{rule.control_type}|{rule.parameter}|{rule.active}"
                )
                rule_eval_filiale = _rule_eval_filiale(rule, filiale)
                non_anom_signature = (
                    f"{rule.id}|{rule.name}|{rule.applicability}|{rule.field_name}|"
                    f"{rule.control_type}|{rule.parameter}|{rule.filiale}|"
                    f"{rule_eval_filiale}|{agence}|{expl}"
                )
                quality_key = f"quality_control:stat:v{rules_version}:d{data_refresh_bucket}:{hashlib.md5(quality_signature.encode('utf-8')).hexdigest()}"
                non_anom_key = f"quality_control:non_anom:v{rules_version}:d{data_refresh_bucket}:{hashlib.md5(non_anom_signature.encode('utf-8')).hexdigest()}"

                if cache.get(quality_key) is None:
                    cache.set(quality_key, _evaluate_data_quality_rule_scoped(rule), timeout=86400)
                    warmed += 1
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

    def _warm_dashboards(self, users):
        request_factory = RequestFactory()
        periods = ["journalier", "mensuel"]
        warmed = 0

        for user in users:
            for mode in ["Flux", "Stock"]:
                for periode in periods:
                    request = request_factory.get(f"/statistiques/?mode={mode}&periode={periode}")
                    request.user = user
                    statistiques(request)
                    warmed += 1

            for periode in periods:
                request = request_factory.get(f"/evolution_filiale/?periode={periode}")
                request.user = user
                taux_evolution_view(request)
                warmed += 1

                request = request_factory.get(f"/evolution_filiale_stock/?periode={periode}")
                request.user = user
                taux_evolution_view_stock(request)
                warmed += 1

            if getattr(user, "organe", "") in GROUP_ORGANS:
                for filiale in TauxEvolution_filiale.objects.values_list("filiale", flat=True).distinct()[:10]:
                    request = request_factory.get(f"/evolution_filiale/?filiale={filiale}&periode=mensuel")
                    request.user = user
                    taux_evolution_view(request)
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
