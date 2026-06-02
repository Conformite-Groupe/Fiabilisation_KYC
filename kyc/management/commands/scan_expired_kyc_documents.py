from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from kyc.models import KycDocumentExtraction, KycExpiredDocumentScanMatch, Kyc_pp
from kyc.views import (
    _date_match_key,
    _document_client_identity_score,
    _document_identity_keys,
    _get_kyc_document_match_weights,
    _nationality_match_key,
    _normalize_match_value,
)


def parse_flexible_date(value):
    if value in (None, ""):
        return None

    cleaned = str(value).strip()
    if not cleaned:
        return None

    parsed_dt = parse_datetime(cleaned)
    if parsed_dt:
        return parsed_dt.date()

    parsed_date = parse_date(cleaned)
    if parsed_date:
        return parsed_date

    for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y%m%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(cleaned, date_format).date()
        except ValueError:
            continue
    return None


class Command(BaseCommand):
    help = "Scanne les DATVALID expirees dans KYC PP et rapproche les documents scannes avec une date plus recente."

    def add_arguments(self, parser):
        parser.add_argument("--limit-clients", type=int, default=50000)
        parser.add_argument("--limit-documents", type=int, default=3000)
        parser.add_argument("--min-rate", type=int, default=30)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        today = timezone.localdate()
        min_rate = max(0, min(options["min_rate"], 100))
        match_weights = _get_kyc_document_match_weights()

        documents = list(
            KycDocumentExtraction.objects.exclude(date_expiration="")
            .only(
                "id",
                "original_filename",
                "import_batch",
                "numero_document",
                "numero_identification_nationale",
                "date_naissance",
                "date_expiration",
                "nationalite",
                "pays_naissance",
                "lieu_naissance",
            )
            .order_by("-created_at")[: options["limit_documents"]]
        )

        docs_by_identity = {}
        docs_by_birth = {}
        docs_by_nationality = {}
        for document in documents:
            for key in _document_identity_keys(document):
                docs_by_identity.setdefault(key, []).append(document)
            birth_key = _date_match_key(document.date_naissance)
            if birth_key:
                docs_by_birth.setdefault(birth_key, []).append(document)
            nationality_key = _nationality_match_key(document.nationalite or document.pays_naissance)
            if nationality_key:
                docs_by_nationality.setdefault(nationality_key, []).append(document)

        clients_checked = 0
        expired_clients = 0
        matches_found = 0
        matches_saved = 0

        clients = (
            Kyc_pp.objects.exclude(DATVALID="")
            .only("id", "FILIALE", "AGENCE", "CLIENT", "IDP", "NUMID", "DATNAIS", "PAYNAIS", "DATVALID")
            .order_by("id")[: options["limit_clients"]]
        )

        for client in clients:
            clients_checked += 1
            client_validity = parse_flexible_date(client.DATVALID)
            if not client_validity or client_validity >= today:
                continue

            expired_clients += 1
            candidate_documents = {}
            numid_key = _normalize_match_value(client.NUMID)
            for document in docs_by_identity.get(numid_key, []):
                candidate_documents[document.pk] = document

            birth_key = _date_match_key(client.DATNAIS)
            for document in docs_by_birth.get(birth_key, []):
                candidate_documents[document.pk] = document

            nationality_key = _nationality_match_key(client.PAYNAIS)
            if candidate_documents:
                for document in docs_by_nationality.get(nationality_key, []):
                    candidate_documents[document.pk] = document

            for document in candidate_documents.values():
                document_validity = parse_flexible_date(document.date_expiration)
                if not document_validity or document_validity <= client_validity:
                    continue

                match_rate = _document_client_identity_score(document, client, match_weights)
                if match_rate < min_rate:
                    continue

                matches_found += 1
                if options["dry_run"]:
                    continue

                _, created = KycExpiredDocumentScanMatch.objects.update_or_create(
                    client=client,
                    document=document,
                    defaults={
                        "client_code": client.CLIENT or "",
                        "idp": client.IDP or "",
                        "filiale": client.FILIALE or "",
                        "agence": client.AGENCE or "",
                        "old_validity_date": client.DATVALID or "",
                        "document_validity_date": document.date_expiration or "",
                        "match_rate": match_rate,
                    },
                )
                if created:
                    matches_saved += 1

        self.stdout.write(self.style.SUCCESS(
            "Scan termine: "
            f"{clients_checked} client(s) lus, "
            f"{expired_clients} DATVALID expiree(s), "
            f"{matches_found} correspondance(s) trouvee(s), "
            f"{matches_saved} nouvelle(s) sauvegardee(s)."
        ))
