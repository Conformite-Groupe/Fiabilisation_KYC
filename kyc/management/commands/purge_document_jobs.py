"""
Purge les anciens jobs du module Screening KYC ID pour eviter que les
resultats JSON volumineux ne saturent la base.

  - Jobs de rapprochement (KycDocumentMatchJob) termines/en echec plus vieux que N jours
  - Jobs OCR (KycDocumentOcrJob) termines/en echec plus vieux que N jours
  - Decisions de correspondance : conservees (tracabilite), non purgees ici

Planifier (ex. hebdomadaire) :
    python manage.py purge_document_jobs --days 30
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Purge les anciens jobs de rapprochement et OCR du module Screening KYC ID."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30,
                            help="Anciennete minimale en jours (defaut 30).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Affiche ce qui serait supprime sans rien supprimer.")

    def handle(self, *args, **options):
        from kyc.models import KycDocumentMatchJob, KycDocumentOcrJob

        days = max(1, options.get("days") or 30)
        dry = options.get("dry_run")
        cutoff = timezone.now() - timedelta(days=days)

        finished = ("completed", "failed")
        match_qs = KycDocumentMatchJob.objects.filter(status__in=finished, created_at__lt=cutoff)
        ocr_qs = KycDocumentOcrJob.objects.filter(status__in=finished, created_at__lt=cutoff)

        match_count = match_qs.count()
        ocr_count = ocr_qs.count()

        if dry:
            self.stdout.write(f"[DRY-RUN] {match_count} job(s) de rapprochement et "
                              f"{ocr_count} job(s) OCR seraient supprimes (> {days} j).")
            return

        match_qs.delete()
        ocr_qs.delete()
        self.stdout.write(self.style.SUCCESS(
            f"Purge terminee : {match_count} job(s) de rapprochement et {ocr_count} job(s) OCR supprimes (> {days} j)."
        ))
