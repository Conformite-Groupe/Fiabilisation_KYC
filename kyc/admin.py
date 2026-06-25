from django.contrib import admin

from .models import KycDocumentExtraction, KycDocumentMatchJob, KycDocumentMatchSettings, KycExpiredDocumentScanMatch, FilialeModuleConfig


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
