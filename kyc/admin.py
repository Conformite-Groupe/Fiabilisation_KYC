from django.contrib import admin

from .models import KycDocumentExtraction, KycDocumentMatchJob, KycDocumentMatchSettings, KycExpiredDocumentScanMatch, FilialeModuleConfig, EmailReminderConfig


@admin.register(FilialeModuleConfig)
class FilialeModuleConfigAdmin(admin.ModelAdmin):
    list_display = ('filiale', 'screening_kyc_paye_active')
    list_editable = ('screening_kyc_paye_active',)
    search_fields = ('filiale',)
    list_filter = ('screening_kyc_paye_active',)


@admin.register(KycDocumentExtraction)
class KycDocumentExtractionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "import_batch",
        "document_type",
        "original_filename",
        "page_range",
        "prenom",
        "nom",
        "numero_document",
        "nationalite",
        "uploaded_by",
    )
    list_filter = ("document_type", "created_at", "nationalite", "import_batch")
    search_fields = (
        "import_batch",
        "original_filename",
        "source_filename",
        "prenom",
        "nom",
        "numero_document",
        "date_naissance",
        "date_expiration",
        "nationalite",
        "pays_naissance",
        "numero_identification_nationale",
        "lieu_naissance",
        "adresse",
        "origine_revenu",
        "extracted_text",
    )
    readonly_fields = ("created_at",)


@admin.register(KycDocumentMatchSettings)
class KycDocumentMatchSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "birth_date_weight",
        "document_validity_weight",
        "birth_place_weight",
        "nationality_weight",
        "combination_threshold",
        "active",
        "updated_at",
    )
    list_editable = (
        "birth_date_weight",
        "document_validity_weight",
        "birth_place_weight",
        "nationality_weight",
        "combination_threshold",
        "active",
    )
    readonly_fields = ("updated_at",)


@admin.register(KycExpiredDocumentScanMatch)
class KycExpiredDocumentScanMatchAdmin(admin.ModelAdmin):
    list_display = (
        "scan_date",
        "status",
        "client_code",
        "idp",
        "filiale",
        "agence",
        "old_validity_date",
        "document_validity_date",
        "match_rate",
        "document",
    )
    list_filter = ("status", "scan_date", "filiale", "agence")
    search_fields = (
        "client_code",
        "idp",
        "filiale",
        "agence",
        "old_validity_date",
        "document_validity_date",
        "document__original_filename",
        "document__import_batch",
    )
    readonly_fields = ("scan_date", "updated_at")
    list_editable = ("status",)


@admin.register(KycDocumentMatchJob)
class KycDocumentMatchJobAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "status",
        "progress_current",
        "progress_total",
        "message",
        "created_by",
    )
    list_filter = ("status", "created_at")
    search_fields = ("message", "error")
    readonly_fields = ("created_at", "started_at", "completed_at", "updated_at")


@admin.register(EmailReminderConfig)
class EmailReminderConfigAdmin(admin.ModelAdmin):
    list_display = ('smtp_host', 'smtp_port', 'smtp_mode_display', 'smtp_user', 'from_email', 'frequency', 'days_before', 'active', 'updated_at')
    list_editable = ('active',)
    readonly_fields = ('smtp_mode_display',)
    fieldsets = (
        ('Configuration SMTP', {
            'description': (
                '<div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:10px 14px;border-radius:6px;margin-bottom:12px;font-size:12px;">'
                '<strong>Combinaisons valides :</strong><br>'
                '&bull; Port <strong>587</strong> → cocher <em>Utiliser TLS</em>, décocher <em>Utiliser SSL</em><br>'
                '&bull; Port <strong>465</strong> → cocher <em>Utiliser SSL</em>, décocher <em>Utiliser TLS</em><br>'
                '&bull; Port <strong>25</strong> → décocher les deux'
                '</div>'
            ),
            'fields': ('smtp_host', 'smtp_port', 'smtp_use_tls', 'smtp_use_ssl', 'smtp_mode_display', 'smtp_user', 'smtp_password', 'from_email', 'from_name'),
        }),
        ('Paramètres de rappel', {
            'fields': ('frequency', 'days_before', 'active'),
        }),
    )

    @admin.display(description='Mode détecté')
    def smtp_mode_display(self, obj):
        if not obj.pk:
            return '—'
        if obj.smtp_use_ssl and obj.smtp_use_tls:
            return '⚠️ Invalide — SSL et TLS simultanés'
        if obj.smtp_use_ssl:
            return f'🔒 SSL direct (port {obj.smtp_port})'
        if obj.smtp_use_tls:
            return f'🔐 STARTTLS (port {obj.smtp_port})'
        return f'⚠️ Non chiffré (port {obj.smtp_port})'

    def save_model(self, request, obj, form, change):
        from django.contrib import messages as dj_messages
        if obj.smtp_use_ssl and obj.smtp_use_tls:
            self.message_user(request, "⚠️ SSL et TLS ne peuvent pas être activés simultanément. Désactivez l'un des deux.", level='warning')
        if obj.smtp_port == 465 and obj.smtp_use_tls and not obj.smtp_use_ssl:
            self.message_user(request, "⚠️ Port 465 détecté avec TLS — vous devriez utiliser SSL à la place.", level='warning')
        if obj.smtp_port == 587 and obj.smtp_use_ssl and not obj.smtp_use_tls:
            self.message_user(request, "⚠️ Port 587 détecté avec SSL — vous devriez utiliser TLS (STARTTLS) à la place.", level='warning')
        super().save_model(request, obj, form, change)
