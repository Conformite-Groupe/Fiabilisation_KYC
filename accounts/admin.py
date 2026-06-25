from django.contrib import admin
from accounts.models import ProfileV, UserLoginHistory, Zone
from kyc.models import (
    Notation,
    Kyc_pm,
    Anomalie,
    TauxEvolution,
    DATEREV,
    Kyc_pp,
    Profile,
    TauxEvolution_filiale,
    Devise,
)


@admin.register(ProfileV)
class ProfileVAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "username",
        "filiale",
    )
    search_fields = [
        "email",
        "filiale",
    ]
    list_filter = [
        "filiale",
    ]

admin.site.register(Notation)

admin.site.register(Devise)

class KycAdminBase(admin.ModelAdmin):
  
    # Colonnes affichées dans la liste
    list_display = ('CLIENT', 'FILIALE', 'AGENCE', 'EXPL', 'DATOUV')
    
    # Filtres latéraux (Visualisation par filiale)
    list_filter = ('FILIALE', 'AGENCE')
    
    # Barre de recherche (Filtre par CLIENT et autres numéros)
    # Note : 'IDM' pour PM et 'IDP'/'NUMID' pour PP sont ajoutés spécifiquement plus bas
    search_fields = ('CLIENT', 'EXPL')
    
    # Nombre d'éléments par page
    list_per_page = 50

@admin.register(Kyc_pm)
class KycPmAdmin(KycAdminBase):
    # On ajoute les colonnes spécifiques aux Personnes Morales
    list_display = ('CLIENT', 'FILIALE', 'IDM', 'RCSNO', 'DATOUV', 'DATEREV')
    # Recherche par Nom Client, IDM (Numéro ID), ou RCS
    search_fields = ('CLIENT', 'IDM', 'RCSNO')

@admin.register(Kyc_pp)
class KycPpAdmin(KycAdminBase):
    # On ajoute les colonnes spécifiques aux Personnes Physiques
    list_display = (
        'CLIENT',
        'IDP',
        'FILIALE',
        'AGENCE',
        'DATEREV',
    )
    # Recherche par Nom Client, NUMID, ou IDP
    list_filter = ('FILIALE', 'AGENCE', 'PAYNAIS', 'RESID', 'PPE')
    search_fields = (
        'CLIENT',
        'IDP',
        'NUMID',
        'FILIALE',
        'AGENCE',
        'LIB_AGENCE',
        'DATNAIS',
        'DATVALID',
        'PAYNAIS',
        'TEL',
        'ADRESSE',
    )
    ordering = ('FILIALE', 'AGENCE', 'CLIENT')
    fieldsets = (
        ('Identification client', {
            'fields': ('FILIALE', 'AGENCE', 'LIB_AGENCE', 'EXPL', 'CLIENT', 'IDP', 'NUMID')
        }),
        ('Donnees KYC PP', {
            'fields': ('DATNAIS', 'DATVALID', 'PAYNAIS', 'PROFESSION', 'ADRESSE', 'PAYS_RESID')
        }),
        ('Autres informations', {
            'fields': ('CODAPE', 'SALAIRE', 'ORIGINE_REV', 'TEL', 'DATOUV', 'DATEREV', 'PPE', 'DEVISE', 'RESID')
        }),
    )
admin.site.register(Anomalie)
@admin.register(TauxEvolution)
class TauxEvolutionAdmin(admin.ModelAdmin):
    list_display = (
        "filiale",
        "agence",
        "expl",
        "date",
        "taux",
        "flux_stock",
        "pp_pm",
        "created_at",
    )
    search_fields = [
        "filiale",
        "agence",
        "expl",
        "flux_stock",
        "pp_pm",
    ]
    list_filter = [
        "date",
        "filiale",
    ]
    ordering = (("-date",))


admin.site.register(DATEREV)
admin.site.register(Profile)
@admin.register(TauxEvolution_filiale)
class TauxEvolution_filialeAdmin(admin.ModelAdmin):
    list_display = (
        "filiale",
        "flux_PM",
        "flux_PP",
        "stock_PM",
        "stock_PP",
        "date",
    )
    search_fields = [
        "filiale",
        ]
admin.site.register(Zone)


@admin.register(UserLoginHistory)
class UserLoginHistoryAdmin(admin.ModelAdmin):
    list_display = ("user", "login_at")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    list_filter = ("login_at",)
    ordering = ("-login_at",)
