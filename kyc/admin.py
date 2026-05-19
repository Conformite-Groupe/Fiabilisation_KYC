from django.contrib import admin

from .models import KycDocumentExtraction


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
