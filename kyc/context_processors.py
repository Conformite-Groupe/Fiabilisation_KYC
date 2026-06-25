# core/context_processors.py
from kyc.models import Notation
from django.db.models import Max
from django.conf import settings

def user_stat_processor(request):
    user_stat = ["Directeur Agence", "Chargé Client"]
    return {'user_stat': user_stat}


def user_filiale_processor(request):
    user_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau", "Qualité", "Directeur Agence",
                    "Chargé Client", "Risques", "DAI"]
    return {'user_filiale': user_filiale}


def user_filiale_oc_processor(request):
    user_filiale_oc_ = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau", "Qualité", "Risques", "DAI"]
    return {'user_filiale_oc_': user_filiale_oc_}

def context_conformite_processor(request):
    user_conformite = ["Conformité", "Conformité Groupe"]
    return {'user_conformite': user_conformite}


def user_groupe_processor(request):
    user_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "Conformité Groupe",
                   "Contrôle Permanent Groupe", "PASS", "GUEST"]
    return {'user_groupe': user_groupe}


def notation(request):
    user = request.user
    notes = Notation.objects.filter(flux_stock='Flux')

    # 1. On initialise la variable notation
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))
    notation_queryset = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])

    # 2. On vérifie si l'utilisateur est connecté AVANT d'accéder à .organe
    if user.is_authenticated:
        if user.organe == "Chargé Client":
            notation_queryset = notation_queryset.filter(agent__filiale=user.filiale, agent__code_expl=user.code_expl)
        elif user.organe == "Directeur Agence":
            notation_queryset = notation_queryset.filter(agent__filiale=user.filiale, agent__agence=user.agence,
                                                         agent__code_expl=user.code_expl)
        elif user.organe not in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "PASS", "GUEST"]:
            notation_queryset = notation_queryset.filter(agent__filiale=user.filiale)
    else:
        # Si l'utilisateur n'est pas connecté, on renvoie un queryset vide
        # ou les notations par défaut pour éviter l'erreur.
        notation_queryset = notation_queryset.none()

    return {'notation': notation_queryset}


def static_version_processor(request):
    return {'static_version': getattr(settings, 'STATIC_VERSION', '1')}


def kyc_display_fields_processor(request):
    from kyc.models import KycFieldVisibilityConfig, Kyc_pp, Kyc_pm

    KYC_PP_FIELD_LABELS = [
        ("CLIENT", "CLIENT"),
        ("EXPL", "EXPL"),
        ("FILIALE", "FILIALE"),
        ("AGENCE", "AGENCE"),
        ("LIB_AGENCE", "LIB_AGENCE"),
        ("IDP", "IDP"),
        ("PAYNAIS", "PAYNAIS"),
        ("PROFESSION", "PROFESSION"),
        ("SALAIRE", "SALAIRE"),
        ("NUMID", "NUMID"),
        ("CODAPE", "CODAPE"),
        ("TEL", "TEL"),
        ("DATNAIS", "DATNAIS"),
        ("ADRESSE", "ADRESSE"),
        ("DATVALID", "DATVALID"),
        ("ORIGINE_REV", "ORIGINE_REV"),
        ("INTITULE_COMPTE", "INTITULE_COMPTE"),
        ("EMPLOYEUR", "EMPLOYEUR"),
        ("PAYS_RESID", "PAYS_RESID"),
        ("LIEU_DELIVRANCE_CIN", "LIEU_DELIVRANCE_CIN"),
        ("BOITE_POSTALE", "BOITE_POSTALE"),
        ("CONSENT_BIC", "CONSENT_BIC"),
        ("DATOUV", "DATOUV"),
        ("PPE", "PPE"),
        ("DEVISE", "DEVISE"),
        ("RESID", "RESID"),
        ("DATEREV", "DATEREV"),
        ("RISQUE", "RISQUE"),
    ]

    KYC_PM_FIELD_LABELS = [
        ("CLIENT", "CLIENT"),
        ("EXPL", "EXPL"),
        ("FILIALE", "FILIALE"),
        ("AGENCE", "AGENCE"),
        ("LIB_AGENCE", "LIB_AGENCE"),
        ("IDM", "IDM"),
        ("CODAPE", "CODAPE"),
        ("AGEC", "AGEC"),
        ("CAPITAL", "CAPITAL"),
        ("CA", "CA"),
        ("RESULTAT", "RESULTAT"),
        ("RCSNO", "RCSNO"),
        ("ORIGINE_REV", "ORIGINE_REV"),
        ("TEL", "TEL"),
        ("INTITULE_COMPTE", "INTITULE_COMPTE"),
        ("ADRESSE_SOCIALE", "ADRESSE_SOCIALE"),
        ("NUMERO_FISCAL", "NUMERO_FISCAL"),
        ("PAYS_JUR", "PAYS_JUR"),
        ("ACTIONNAIRE", "ACTIONNAIRE"),
        ("MANDATAIRE", "MANDATAIRE"),
        ("BOITE_POSTALE", "BOITE_POSTALE"),
        ("CONSENT_BIC", "CONSENT_BIC"),
        ("DATOUV", "DATOUV"),
        ("DEVISE", "DEVISE"),
        ("RESID", "RESID"),
        ("DATEREV", "DATEREV"),
        ("PPE", "PPE"),
        ("RISQUE", "RISQUE"),
    ]

    user = request.user
    filiale = request.GET.get('filiale') or request.GET.get('filiale_modal')
    if filiale:
        filiale = filiale.strip()
    if not filiale:
        filiale = user.filiale if (user.is_authenticated and getattr(user, 'filiale', '')) else ''
        if filiale:
            filiale = filiale.strip()

    # 1. PP display fields
    pp_config = None
    if filiale:
        filiale_configs = [c for c in KycFieldVisibilityConfig.objects.filter(client_type='pp') if filiale in (c.filiales or [])]
        if filiale_configs:
            pp_config = filiale_configs[0]

    if not pp_config:
        global_configs = [c for c in KycFieldVisibilityConfig.objects.filter(client_type='pp') if not c.filiales]
        if global_configs:
            pp_config = global_configs[0]

    if pp_config and pp_config.display_fields is not None:
        pp_fields = pp_config.display_fields
    else:
        pp_fields = [f[0] for f in KYC_PP_FIELD_LABELS]

    kyc_pp_display_fields = [f for f in KYC_PP_FIELD_LABELS if f[0] in pp_fields]

    # 2. PM display fields
    pm_config = None
    if filiale:
        filiale_configs = [c for c in KycFieldVisibilityConfig.objects.filter(client_type='pm') if filiale in (c.filiales or [])]
        if filiale_configs:
            pm_config = filiale_configs[0]

    if not pm_config:
        global_configs = [c for c in KycFieldVisibilityConfig.objects.filter(client_type='pm') if not c.filiales]
        if global_configs:
            pm_config = global_configs[0]

    if pm_config and pm_config.display_fields is not None:
        pm_fields = pm_config.display_fields
    else:
        pm_fields = [f[0] for f in KYC_PM_FIELD_LABELS]

    kyc_pm_display_fields = [f for f in KYC_PM_FIELD_LABELS if f[0] in pm_fields]

    return {
        'kyc_pp_display_fields': kyc_pp_display_fields,
        'kyc_pm_display_fields': kyc_pm_display_fields,
    }

def module_screening_processor(request):
    from kyc.models import FilialeModuleConfig
    active = False
    if request.user.is_authenticated:
        if getattr(request.user, 'filiale', None) == "BOA Group":
            config = FilialeModuleConfig.objects.filter(filiale=request.user.filiale).first()
            if config and config.screening_kyc_paye_active:
                active = True
        elif hasattr(request.user, 'filiale') and request.user.filiale:
            config = FilialeModuleConfig.objects.filter(filiale=request.user.filiale).first()
            if config and config.screening_kyc_paye_active:
                active = True
    return {'module_screening_kyc_paye_enabled': active}


