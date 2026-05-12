# core/context_processors.py
from kyc.models import Notation
from django.db.models import Max

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
        elif user.organe not in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "GUEST"]:
            notation_queryset = notation_queryset.filter(agent__filiale=user.filiale)
    else:
        # Si l'utilisateur n'est pas connecté, on renvoie un queryset vide
        # ou les notations par défaut pour éviter l'erreur.
        notation_queryset = notation_queryset.none()

    return {'notation': notation_queryset}
