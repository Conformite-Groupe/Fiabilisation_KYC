# -*- coding: utf-8 -*-
"""
Worker OCR du module Screening KYC ID (/document-extraction).

Traite les jobs `KycDocumentOcrJob` crees a l'upload :
  - mode "files"       : OCR de chaque document en attente du lot ;
  - mode "grouped_pdf" : decoupage du PDF groupe en pieces + OCR.

Usage :
    python manage.py process_document_ocr             # une passe puis sortie (cron)
    python manage.py process_document_ocr --loop      # boucle continue (service)
    python manage.py process_document_ocr --workers 4 # OCR en parallele

Les jobs "running" sans mise a jour depuis --stale-minutes sont consideres
orphelins (crash/redemarrage) et remis en file d'attente automatiquement.
"""
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from kyc.models import KycDocumentExtraction, KycDocumentOcrJob


class Command(BaseCommand):
    help = "Traite en arriere-plan les lots OCR du module Screening KYC ID."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true",
                            help="Boucle en continu au lieu d'une seule passe.")
        parser.add_argument("--interval", type=int, default=10,
                            help="Secondes entre deux passes en mode --loop (defaut 10).")
        parser.add_argument("--workers", type=int, default=2,
                            help="Nombre d'OCR en parallele pour un lot (defaut 2).")
        parser.add_argument("--stale-minutes", type=int, default=30,
                            help="Delai avant de requalifier un job 'running' orphelin (defaut 30).")
        parser.add_argument("--job-id", type=int, default=None,
                            help="Traite uniquement ce job (debug).")

    def handle(self, *args, **options):
        # Console Windows (cp1252) : evite un crash sur les caracteres accentues.
        for stream in (self.stdout, self.stderr):
            try:
                stream._out.reconfigure(errors="replace")
            except Exception:
                pass
        loop = options["loop"]
        interval = max(options["interval"], 2)
        self.workers = max(options["workers"], 1)
        self.stale_minutes = max(options["stale_minutes"], 5)
        job_id = options.get("job_id")

        while True:
            close_old_connections()
            self._requeue_stale_jobs()
            job = self._claim_next_job(job_id)
            if job:
                self._process_job(job)
                continue  # enchainer immediatement s'il reste des jobs
            if not loop or job_id:
                break
            time.sleep(interval)

    # ------------------------------------------------------------------ #
    # File d'attente
    # ------------------------------------------------------------------ #
    def _requeue_stale_jobs(self):
        threshold = timezone.now() - timedelta(minutes=self.stale_minutes)
        stale = KycDocumentOcrJob.objects.filter(status="running", updated_at__lt=threshold)
        for job in stale:
            self.stdout.write(self.style.WARNING(
                f"Job #{job.pk} (lot {job.import_batch}) orphelin -> remis en attente."))
            KycDocumentExtraction.objects.filter(
                import_batch=job.import_batch, extraction_status="processing"
            ).update(extraction_status="pending")
            job.status = "pending"
            job.message = "Reprise apres interruption"
            job.save(update_fields=["status", "message", "updated_at"])

    def _claim_next_job(self, job_id=None):
        queryset = KycDocumentOcrJob.objects.filter(status="pending").order_by("created_at")
        if job_id:
            queryset = queryset.filter(pk=job_id)
        job = queryset.first()
        if not job:
            return None
        # verrou optimiste : seul le process qui reussit l'update prend le job
        claimed = KycDocumentOcrJob.objects.filter(pk=job.pk, status="pending").update(
            status="running", started_at=timezone.now(),
            message="Demarrage du traitement OCR", updated_at=timezone.now(),
        )
        if not claimed:
            return None
        job.refresh_from_db()
        return job

    # ------------------------------------------------------------------ #
    # Traitement
    # ------------------------------------------------------------------ #
    def _process_job(self, job):
        self.stdout.write(f"Traitement job #{job.pk} (lot {job.import_batch}, mode {job.mode})...")
        try:
            if job.mode == "grouped_pdf":
                done, failed = self._process_grouped_pdf(job)
            else:
                done, failed = self._process_files(job)
            KycDocumentOcrJob.objects.filter(pk=job.pk).update(
                status="completed",
                done_count=done,
                failed_count=failed,
                message=f"Termine : {done} traite(s), {failed} echec(s)",
                completed_at=timezone.now(),
                updated_at=timezone.now(),
            )
            style = self.style.SUCCESS if not failed else self.style.WARNING
            self.stdout.write(style(f"Job #{job.pk} termine : {done} ok, {failed} echec(s)."))
        except Exception as exc:
            KycDocumentOcrJob.objects.filter(pk=job.pk).update(
                status="failed",
                message="Echec du traitement OCR",
                error=f"{exc}\n{traceback.format_exc()[-2000:]}",
                completed_at=timezone.now(),
                updated_at=timezone.now(),
            )
            self.stderr.write(self.style.ERROR(f"Job #{job.pk} en echec : {exc}"))
        finally:
            close_old_connections()

    def _update_progress(self, job_pk, current, total, message=""):
        fields = {"progress_current": current, "progress_total": total, "updated_at": timezone.now()}
        if message:
            fields["message"] = message
        KycDocumentOcrJob.objects.filter(pk=job_pk).update(**fields)

    # -- mode fichiers --------------------------------------------------- #
    def _process_files(self, job):
        from kyc.views import _fill_document_extraction_fields, _apply_detected_document_type

        pending_ids = list(
            KycDocumentExtraction.objects
            .filter(import_batch=job.import_batch, extraction_status="pending")
            .values_list("pk", flat=True)
        )
        total = len(pending_ids)
        self._update_progress(job.pk, 0, total, f"OCR de {total} document(s)")
        if not total:
            return 0, 0

        done = failed = 0
        processed = 0

        def worker(record_id):
            close_old_connections()
            from kyc.document_extraction import extract_document_data
            record = KycDocumentExtraction.objects.get(pk=record_id)
            KycDocumentExtraction.objects.filter(pk=record_id).update(extraction_status="processing")
            try:
                extraction = extract_document_data(
                    record.uploaded_file.path, record.original_filename, filiale=None,
                )
                _fill_document_extraction_fields(record, extraction)
                _apply_detected_document_type(record, extraction, record.document_type)
                record.extraction_status = "done"
                record.save()
                return True, record_id, ""
            except Exception as exc:
                KycDocumentExtraction.objects.filter(pk=record_id).update(
                    extraction_status="failed",
                    extraction_warnings=f"OCR impossible: {exc}",
                )
                return False, record_id, str(exc)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(worker, rid): rid for rid in pending_ids}
            for future in as_completed(futures):
                ok, record_id, error = future.result()
                processed += 1
                if ok:
                    done += 1
                else:
                    failed += 1
                    self.stderr.write(f"  - echec doc #{record_id}: {error}")
                if processed == total or processed % 3 == 0:
                    self._update_progress(job.pk, processed, total,
                                          f"OCR {processed}/{total} ({failed} echec(s))")
        return done, failed

    # -- mode PDF groupe -------------------------------------------------- #
    def _process_grouped_pdf(self, job):
        from django.conf import settings as dj_settings
        from kyc.document_extraction import extract_pdf_grouped_documents
        from kyc.views import _fill_document_extraction_fields, _apply_detected_document_type

        container = (
            KycDocumentExtraction.objects
            .filter(import_batch=job.import_batch, uploaded_file=job.grouped_source_file)
            .order_by("pk")
            .first()
        )
        source_path = os.path.join(dj_settings.MEDIA_ROOT, job.grouped_source_file)
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"PDF groupe introuvable: {job.grouped_source_file}")

        self._update_progress(job.pk, 0, 0, "Decoupage du PDF groupe et OCR des pieces")
        grouped_extractions = extract_pdf_grouped_documents(
            source_path,
            job.grouped_original_name or os.path.basename(job.grouped_source_file),
            pages_per_document=job.pages_per_document or 1,
        )

        total = len(grouped_extractions)
        done = failed = 0
        for index, extraction in enumerate(grouped_extractions, start=1):
            try:
                record = KycDocumentExtraction(
                    document_type=job.document_type or "piece_identite",
                    uploaded_file=job.grouped_source_file,
                    original_filename=job.grouped_original_name,
                    source_filename=job.grouped_original_name,
                    import_batch=job.import_batch,
                    uploaded_by=job.created_by,
                    client_type=job.client_type,
                    extraction_status="done",
                    file_hash=container.file_hash if container else "",
                )
                _fill_document_extraction_fields(record, extraction)
                _apply_detected_document_type(record, extraction, job.document_type)
                record.save()
                done += 1
            except Exception as exc:
                failed += 1
                self.stderr.write(f"  - echec piece {index}: {exc}")
            self._update_progress(job.pk, index, total, f"Pieces {index}/{total}")

        # le conteneur technique ne doit pas apparaitre comme un document
        if container and done:
            container.delete()
        elif container:
            KycDocumentExtraction.objects.filter(pk=container.pk).update(
                extraction_status="failed",
                extraction_warnings="Decoupage du PDF groupe sans resultat.",
            )
        return done, failed
