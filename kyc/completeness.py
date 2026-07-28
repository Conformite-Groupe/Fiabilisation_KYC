import math
from datetime import timedelta

from django.db import transaction
from django.db.models import Q, CharField
from django.db.models.functions import Length
from django.core.cache import cache
from django.utils import timezone

                                                                                                
CharField.register_lookup(Length)

from .models import (
    KycCompletenessCalculation,
    KycCompletenessFieldConfig,
    Kyc_pm,
    Kyc_pp,
)


MODEL_BY_APPLICABILITY = {
    "PP": Kyc_pp,
    "PM": Kyc_pm,
}

DEFAULT_NON_RENS_FIELDS = {
    "PP": (
        "PAYNAIS", "PROFESSION", "SALAIRE", "NUMID", "CODAPE", "TEL",
        "DATNAIS", "ADRESSE", "DATVALID", "ORIGINE_REV", "INTITULE_COMPTE",
        "EMPLOYEUR", "PAYS_RESID", "LIEU_DELIVRANCE_CIN", "BOITE_POSTALE",
        "CONSENT_BIC",
    ),
    "PM": (
        "CODAPE", "AGEC", "CAPITAL", "CA", "RESULTAT", "RCSNO",
        "ORIGINE_REV", "TEL", "INTITULE_COMPTE", "ADRESSE_SOCIALE",
        "NUMERO_FISCAL", "PAYS_JUR", "ACTIONNAIRE", "MANDATAIRE",
        "BOITE_POSTALE", "CONSENT_BIC",
    ),
}


def model_field_names(applicability):
    model = MODEL_BY_APPLICABILITY[applicability]
    return [field.name for field in model._meta.fields if not field.primary_key and not field.auto_created]


def get_completeness_configs(applicability, filiale=None, only_display=False, only_critical=False):
    qs = KycCompletenessFieldConfig.objects.filter(applicability=applicability, active=True)
    if filiale:
        qs = qs.filter(Q(filiale=filiale) | Q(filiale=""))
    else:
        qs = qs.filter(filiale="")
    if only_display:
        qs = qs.filter(show_on_non_rens=True)
    if only_critical:
        qs = qs.filter(is_critical=True)

    configs = list(qs.order_by("filiale", "field_name"))
    if filiale:
        exact = [config for config in configs if config.filiale == filiale]
        if exact:
            configs = exact

    valid_fields = set(model_field_names(applicability))
    configs = [config for config in configs if config.field_name in valid_fields]
    if configs:
        return configs

    fallback_fields = DEFAULT_NON_RENS_FIELDS.get(applicability, ())
    return [
        KycCompletenessFieldConfig(
            filiale=filiale or "",
            applicability=applicability,
            field_name=field_name,
            is_critical=True,
            show_on_non_rens=True,
            active=True,
        )
        for field_name in fallback_fields
        if field_name in valid_fields
    ]


def missing_filter_for_fields(fields):
    missing_q = None
    for field_name in fields:
        field_q = (
            Q(**{f"{field_name}__isnull": True}) | 
            Q(**{f"{field_name}__exact": ""}) |
            Q(**{f"{field_name}__iexact": "XX"}) |
            Q(**{f"{field_name}__iexact": "RAS"}) |
            Q(**{f"{field_name}__iexact": "R.A.S."}) |
            Q(**{f"{field_name}__iexact": "R.A.S"}) |
            Q(**{f"{field_name}__length": 1})
        )
        missing_q = field_q if missing_q is None else missing_q | field_q
    return missing_q


def filter_non_rens_queryset(queryset, applicability):
    filiales = list(queryset.order_by().values_list("FILIALE", flat=True).distinct())
    if not filiales:
        return queryset.none()

    combined_q = None
    for filiale in filiales:
        configs = get_completeness_configs(applicability, filiale=filiale, only_display=True)
        fields = [config.field_name for config in configs if config.show_on_non_rens]
        field_q = missing_filter_for_fields(fields)
        if field_q is None:
            continue
        scoped_q = Q(FILIALE=filiale) & field_q
        combined_q = scoped_q if combined_q is None else combined_q | scoped_q

    if combined_q is None:
        return queryset.none()
    return queryset.filter(combined_q).distinct().order_by("id")


def apply_config_exclusion(queryset, config):
    if not config.exclusion_field_name or not config.exclusion_expression:
        return queryset, 0

    valid_fields = set(model_field_names(config.applicability))
    if config.exclusion_field_name not in valid_fields:
        return queryset, 0

    excluded_qs = queryset.filter(**{f"{config.exclusion_field_name}__icontains": config.exclusion_expression})
    excluded_count = excluded_qs.count()
    return queryset.exclude(pk__in=excluded_qs.values("pk")), excluded_count


def evaluate_config_queryset(queryset, config):
    scoped_queryset, excluded_count = apply_config_exclusion(queryset, config)
    total = scoped_queryset.count()
    missing_q = missing_filter_for_fields([config.field_name])
    missing_count = scoped_queryset.filter(missing_q).count() if missing_q is not None else 0
    compliant_count = max(total - missing_count, 0)
    rate = math.floor((compliant_count / total) * 100) if total else 0
    return {
        "total_clients": total,
        "compliant_clients": compliant_count,
        "incomplete_clients": missing_count,
        "excluded_clients": excluded_count,
        "completeness_rate": rate,
    }


def create_calculation_row(applicability, filiale, scope_type, queryset, configs, user=None, agence="", expl=""):
    field_results = []
    total_evaluated = 0
    total_compliant = 0
    total_missing = 0
    total_excluded = 0

    for config in configs:
        result = evaluate_config_queryset(queryset, config)
        field_results.append(KycCompletenessCalculation(
            filiale=filiale,
            applicability=applicability,
            scope_type=scope_type,
            agence=agence or "",
            expl=expl or "",
            field_name=config.field_name,
            is_global=False,
            calculated_by=user,
            **result,
        ))
        total_evaluated += result["total_clients"]
        total_compliant += result["compliant_clients"]
        total_missing += result["incomplete_clients"]
        total_excluded += result["excluded_clients"]

    global_rate = math.floor((total_compliant / total_evaluated) * 100) if total_evaluated else 0
    field_results.append(KycCompletenessCalculation(
        filiale=filiale,
        applicability=applicability,
        scope_type=scope_type,
        agence=agence or "",
        expl=expl or "",
        field_name="",
        is_global=True,
        total_clients=total_evaluated,
        compliant_clients=total_compliant,
        incomplete_clients=total_missing,
        excluded_clients=total_excluded,
        completeness_rate=global_rate,
        calculated_by=user,
    ))
    return field_results


def update_completeness_progress(progress_key, current, total, message, status="running", created=0, started_at=None, filiale=""):
    if not progress_key:
        return
    percent = round((current / total) * 100, 1) if total else 0
    existing = cache.get(f"kyc_completeness_progress:{progress_key}") or {}
    cache.set(
        f"kyc_completeness_progress:{progress_key}",
        {
            "status": status,
            "current": current,
            "total": total,
            "percent": min(percent, 100),
            "message": message,
            "created": created,
            "started_at": started_at or existing.get("started_at") or timezone.localtime().strftime("%d/%m/%Y %H:%M:%S"),
            "updated_at": timezone.localtime().strftime("%d/%m/%Y %H:%M:%S"),
            "filiale": filiale or existing.get("filiale", ""),
        },
        timeout=3600,
    )


def calculate_completeness(applicability=None, filiale=None, user=None, progress_key=None):
    applications = [applicability] if applicability else ["PP", "PM"]
    created = []
    plan = []

    for app in applications:
        model = MODEL_BY_APPLICABILITY[app]
        filiales = [filiale] if filiale else list(
            model.objects.exclude(FILIALE="").values_list("FILIALE", flat=True).distinct()
        )
        for current_filiale in filiales:
            base_qs = model.objects.filter(FILIALE=current_filiale)
            configs = get_completeness_configs(app, filiale=current_filiale, only_critical=True)
            if not configs:
                continue
            plan.append((app, current_filiale, "FILIALE", "", ""))
            for agence in base_qs.exclude(AGENCE="").values_list("AGENCE", flat=True).distinct():
                plan.append((app, current_filiale, "AGENCE", agence, ""))
            for expl in base_qs.exclude(EXPL="").values_list("EXPL", flat=True).distinct():
                agence_value = base_qs.filter(EXPL=expl).values_list("AGENCE", flat=True).first() or ""
                plan.append((app, current_filiale, "EXPL", agence_value, expl))

    total_steps = len(plan)
    current_step = 0
    update_completeness_progress(progress_key, 0, total_steps, "Preparation du calcul...", filiale=filiale or "")

    with transaction.atomic():
        for app in applications:
            model = MODEL_BY_APPLICABILITY[app]
            filiales = [filiale] if filiale else list(
                model.objects.exclude(FILIALE="").values_list("FILIALE", flat=True).distinct()
            )

            for current_filiale in filiales:
                base_qs = model.objects.filter(FILIALE=current_filiale)
                configs = get_completeness_configs(app, filiale=current_filiale, only_critical=True)
                if not configs:
                    continue

                KycCompletenessCalculation.objects.filter(
                    filiale=current_filiale,
                    applicability=app,
                ).delete()

                current_step += 1
                update_completeness_progress(progress_key, current_step, total_steps, f"{current_filiale} {app} - filiale", created=len(created), filiale=current_filiale)
                created.extend(create_calculation_row(app, current_filiale, "FILIALE", base_qs, configs, user=user))

                for agence in base_qs.exclude(AGENCE="").values_list("AGENCE", flat=True).distinct():
                    agence_qs = base_qs.filter(AGENCE=agence)
                    current_step += 1
                    update_completeness_progress(progress_key, current_step, total_steps, f"{current_filiale} {app} - agence {agence}", created=len(created), filiale=current_filiale)
                    created.extend(create_calculation_row(app, current_filiale, "AGENCE", agence_qs, configs, user=user, agence=agence))

                for expl in base_qs.exclude(EXPL="").values_list("EXPL", flat=True).distinct():
                    expl_qs = base_qs.filter(EXPL=expl)
                    agence_value = expl_qs.values_list("AGENCE", flat=True).first() or ""
                    current_step += 1
                    update_completeness_progress(progress_key, current_step, total_steps, f"{current_filiale} {app} - agent {expl}", created=len(created), filiale=current_filiale)
                    created.extend(create_calculation_row(app, current_filiale, "EXPL", expl_qs, configs, user=user, agence=agence_value, expl=expl))

        if created:
            KycCompletenessCalculation.objects.bulk_create(created, batch_size=1000)

    update_completeness_progress(progress_key, total_steps, total_steps, "Calcul termine.", status="completed", created=len(created), filiale=filiale or "")
    return len(created)


def latest_completeness_rate(applicability, filiale=None, agence=None, expl=None):
    qs = KycCompletenessCalculation.objects.filter(applicability=applicability, is_global=True)
    if expl:
        qs = qs.filter(scope_type="EXPL", expl=expl)
    elif agence:
        qs = qs.filter(scope_type="AGENCE", agence=agence)
    elif filiale:
        qs = qs.filter(scope_type="FILIALE", filiale=filiale)
    else:
        latest_rows = []
        latest_date = qs.order_by("-calculated_at").values_list("calculated_at", flat=True).first()
        if not latest_date:
            return None
        for row in qs.filter(calculated_at__gte=latest_date - timedelta(seconds=1)):
            latest_rows.append(row)
        if not latest_rows:
            return None
        total_clients = sum(row.total_clients for row in latest_rows)
        total_compliant = sum(row.compliant_clients for row in latest_rows)
        return math.floor((total_compliant / total_clients) * 100) if total_clients else 0

    row = qs.order_by("-calculated_at").first()
    return row.completeness_rate if row else None
