from django.contrib import admin
from accounts.models import AuditEvent, ProfileV, UserLoginHistory, Zone
from kyc.models import (
    Notation,
    Kyc_pm,
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
  
                                      
    list_display = ('CLIENT', 'FILIALE', 'AGENCE', 'EXPL', 'DATOUV')
    
                                                  
    list_filter = ('FILIALE', 'AGENCE')
    
                                                              
                                                                                        
    search_fields = ('CLIENT', 'EXPL')
    
                                
    list_per_page = 50

@admin.register(Kyc_pm)
class KycPmAdmin(KycAdminBase):
                                                              
    list_display = ('CLIENT', 'FILIALE', 'IDM', 'RCSNO', 'DATOUV', 'DATEREV')
                                                       
    search_fields = ('CLIENT', 'IDM', 'RCSNO')

@admin.register(Kyc_pp)
class KycPpAdmin(KycAdminBase):
                                                                
    list_display = (
        'CLIENT',
        'IDP',
        'FILIALE',
        'AGENCE',
        'DATEREV',
    )
                                             
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


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "category", "action", "username", "organe", "filiale",
                    "target", "ip_address", "success")
    list_filter = ("category", "success", "filiale", "organe", "timestamp")
    search_fields = ("username", "action", "target", "details", "ip_address")
    ordering = ("-timestamp",)
    date_hierarchy = "timestamp"
    readonly_fields = tuple(f.name for f in AuditEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
