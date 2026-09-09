                            
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

                                           
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))
    notation_queryset = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])

                                                                           
    if user.is_authenticated:
        if user.organe == "Chargé Client":
            notation_queryset = notation_queryset.filter(agent__filiale=user.filiale, agent__code_expl=user.code_expl)
        elif user.organe == "Directeur Agence":
            notation_queryset = notation_queryset.filter(agent__filiale=user.filiale, agent__agence=user.agence,
                                                         agent__code_expl=user.code_expl)
        elif user.organe not in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "PASS", "GUEST"]:
            notation_queryset = notation_queryset.filter(agent__filiale=user.filiale)
    else:
                                                                          
                                                           
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

    def _clean_labels(cfg):
        return {k: v for k, v in ((cfg.field_labels if cfg else None) or {}).items() if v}

    def _resolve(client_type, base_labels):
        all_configs = list(KycFieldVisibilityConfig.objects.filter(client_type=client_type))
        global_config = next((c for c in all_configs if not c.filiales), None)
        filiale_config = next((c for c in all_configs if filiale and filiale in (c.filiales or [])), None)


        fields = None
        for cfg in (filiale_config, global_config):
            if cfg and cfg.display_fields is not None:
                fields = cfg.display_fields
                break
        if fields is None:
            fields = [f[0] for f in base_labels]


        labels = {**_clean_labels(global_config), **_clean_labels(filiale_config)}
        display = [(f[0], labels.get(f[0]) or f[1]) for f in base_labels if f[0] in fields]
        return display, labels

    kyc_pp_display_fields, kyc_pp_field_labels = _resolve('pp', KYC_PP_FIELD_LABELS)
    kyc_pm_display_fields, kyc_pm_field_labels = _resolve('pm', KYC_PM_FIELD_LABELS)

    return {
        'kyc_pp_display_fields': kyc_pp_display_fields,
        'kyc_pm_display_fields': kyc_pm_display_fields,
        'kyc_pp_field_labels': kyc_pp_field_labels,
        'kyc_pm_field_labels': kyc_pm_field_labels,
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


def sidebar_access_processor(request):
    from kyc.models import SidebarAccess

    if not request.user.is_authenticated:
        return {'sidebar_access': {p: False for p in SidebarAccess.ALL_PERMS}}
    return {'sidebar_access': SidebarAccess.perms_for(request.user)}


