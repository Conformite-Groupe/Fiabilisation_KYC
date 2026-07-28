import os
import re
import threading
from io import BytesIO


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".pdf", ".txt"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
TESSERACT_LANG = "fra+eng"
NATIONALITY_BY_COUNTRY_CODE = {
    "SEN": "SENEGALAISE",
    "BEN": "BENINOISE",
    "CIV": "IVOIRIENNE",
    "BFA": "BURKINABE",
    "MLI": "MALIENNE",
    "TGO": "TOGOLAISE",
    "NER": "NIGERIENNE",
}
COUNTRY_BY_CODE = {
    "SEN": "SENEGAL",
    "BEN": "BENIN",
    "CIV": "COTE D IVOIRE",
    "BFA": "BURKINA FASO",
    "MLI": "MALI",
    "TGO": "TOGO",
    "NER": "NIGER",
}


def _clean_value(value):
    value = (value or "").replace("_", " ")
    value = re.sub(r"\s+", " ", value or "").strip(" :-\t\r\n")
    return value[:120]


def _first_match(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return _clean_value(match.group(1))
    return ""


DATE_PATTERN = r"\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}|\d{4}[\/\-.]\d{1,2}[\/\-.]\d{1,2}"
MONTH_PATTERN = r"JAN|JANV|FEB|FEV|MAR|MARS|APR|AVR|MAY|MAI|JUN|JUIN|JUL|JUIL|AUG|AOU|SEP|SEPT|OCT|NOV|DEC"
TEXT_DATE_PATTERN = rf"\d{{1,2}}\s+(?:{MONTH_PATTERN})(?:\s*\/\s*(?:{MONTH_PATTERN}))?\s+\d{{2,4}}"
ANY_DATE_PATTERN = rf"{DATE_PATTERN}|{TEXT_DATE_PATTERN}"


def _lines(text):
    return [_clean_value(line) for line in (text or "").splitlines() if _clean_value(line)]


def _looks_like_label(line):
    value = (line or "").lower()
    labels = (
        "prenom",
        "prenoms",
        "first name",
        "first names",
        "given name",
        "given names",
        "nom",
        "norn",
        "surname",
        "sumame",
        "date",
        "lieu",
        "place of birth",
        "sexe",
        "sex",
        "taille",
        "height",
        "adresse",
        "address",
        "domic",
        "dorm",
        "c1le",
        "cile",
        "nationalite",
        "nationality",
        "autorite",
        "authority",
        "carte",
        "card number",
        "eid number",
        "elD number".lower(),
        "request ref",
        "passport",
        "passeport",
        "departement",
        "commune",
        "bureau",
        "nin",
        "npi",
    )
    return any(label in value for label in labels)


def _next_value_after_label(text, label_patterns, skip_patterns=None, max_lines=6):
    skip_patterns = skip_patterns or []
    lines = _lines(text)
    for index, line in enumerate(lines):
        for label_pattern in label_patterns:
            match = re.search(label_pattern, line, flags=re.IGNORECASE)
            if not match:
                continue

            same_line = _clean_value(line[match.end():])
            same_line = re.sub(r"^[\/|,._-]+", "", same_line).strip()
            if same_line and not _looks_like_label(same_line):
                return same_line

            for candidate in lines[index + 1:index + 1 + max_lines]:
                if any(re.search(pattern, candidate, flags=re.IGNORECASE) for pattern in skip_patterns):
                    continue
                if _looks_like_label(candidate):
                    continue
                return candidate
    return ""


def _first_date_near_label(text, label_patterns, max_chars=180):
    for label_pattern in label_patterns:
        match = re.search(label_pattern, text or "", flags=re.IGNORECASE)
        if not match:
            continue
        window = (text or "")[match.end():match.end() + max_chars]
        date_match = re.search(ANY_DATE_PATTERN, window, flags=re.IGNORECASE)
        if date_match:
            return _clean_value(date_match.group(0))
    return ""


def _sex_near_label(text):
    for label_pattern in [r"\bsexe\b", r"\bsex\b"]:
        match = re.search(label_pattern, text or "", flags=re.IGNORECASE)
        if not match:
            continue
        window = (text or "")[match.end():match.end() + 80]
        sex_match = re.search(r"\b([MFX])\b|=\s*([MFX])", window, flags=re.IGNORECASE)
        if sex_match:
            return (sex_match.group(1) or sex_match.group(2)).upper()
    return ""


def _first_date_in_text(text):
    match = re.search(ANY_DATE_PATTERN, text or "", flags=re.IGNORECASE)
    return _clean_value(match.group(0)) if match else ""


def _remove_dates(value):
    value = re.sub(ANY_DATE_PATTERN, "", value or "", flags=re.IGNORECASE)
    return _clean_value(value)


def _value_before_date(value):
    match = re.search(ANY_DATE_PATTERN, value or "", flags=re.IGNORECASE)
    if match:
        return _clean_value(value[:match.start()])
    return _clean_value(value)


def _mrz_identity_fields(text):
    fields = {}
    lines = [
        re.sub(r"\s+", "", line.upper())
        for line in (text or "").splitlines()
        if "<" in line and len(re.sub(r"\s+", "", line)) >= 25
    ]

    for index, line in enumerate(lines):
        if line.startswith("P<") and index + 1 < len(lines):
            name_part = line[5:] if len(line) > 5 else ""
            if "<<" in name_part:
                surname, given = name_part.split("<<", 1)
                fields["nom"] = _clean_value(surname.replace("<", " "))
                given = re.sub(r"[^A-Z<]+$", "", given)
                if re.search(r"[A-Z]{3,}K[A-Z]{3,}", given):
                    given = re.sub(r"(?<=[A-Z])K(?=[A-Z]{3,})", "<", given, count=1)
                given = given.replace("<", " ")
                fields["prenom"] = _clean_value(given)

            issuing_country = line[2:5].replace("<", "")
            if issuing_country in COUNTRY_BY_CODE:
                fields["pays_delivrance"] = COUNTRY_BY_CODE[issuing_country]

            data_line = lines[index + 1]
            if len(data_line) >= 27:
                passport_number = data_line[:9].replace("<", "")
                if passport_number:
                    fields["numero_document"] = passport_number

                country_code = data_line[10:13].replace("<", "")
                if country_code in NATIONALITY_BY_COUNTRY_CODE:
                    fields["nationalite"] = NATIONALITY_BY_COUNTRY_CODE[country_code]
                if country_code in COUNTRY_BY_CODE and not fields.get("pays_delivrance"):
                    fields["pays_delivrance"] = COUNTRY_BY_CODE[country_code]

                birth = data_line[13:19]
                sex = data_line[20:21]
                expiry = data_line[21:27]
                if birth.isdigit():
                    fields["date_naissance"] = f"{birth[4:6]}/{birth[2:4]}/19{birth[:2]}"
                if sex in {"M", "F", "X"}:
                    fields["sexe"] = sex
                if expiry.isdigit():
                    prefix = "20" if int(expiry[:2]) < 50 else "19"
                    fields["date_expiration"] = f"{expiry[4:6]}/{expiry[2:4]}/{prefix}{expiry[:2]}"
                optional_digits = re.sub(r"\D", "", data_line[28:])
                if len(optional_digits) >= 10:
                    fields["numero_identification_nationale"] = optional_digits[:14]
            break
    return {key: value for key, value in fields.items() if value}


def _has_enough_core_fields(text):
    fields = parse_identity_fields(text)
    core_fields = {"prenom", "nom", "numero_document", "date_naissance", "date_expiration"}
    return len(core_fields.intersection(fields)) >= 4


def detect_document_type(text, original_name="", fields=None, filiale=None):
    from kyc.models import KycDocumentType
    from django.db.models import Q

    content = f"{original_name or ''}\n{text or ''}".upper()
    compact_content = re.sub(r"\s+", "", content)

    if not KycDocumentType.objects.exists():
        KycDocumentType.objects.create(
            code="piece_identite",
            label="Pièce d'identité",
            keywords="CARTE NATIONALE, CARTE D'IDENTITE, CNI, IDENTITY CARD, NATIONAL ID, NIN, NPI, EID NUMBER, CARD NUMBER",
            min_score=2.0,
            filiale=""
        )
        KycDocumentType.objects.create(
            code="passeport",
            label="Passeport",
            keywords="PASSEPORT, PASSPORT, N° PASSEPORT, PASSPORT NO, PASSPORT NUMBER",
            min_score=2.0,
            filiale=""
        )

    query = KycDocumentType.objects.filter(Q(filiale=filiale or "") | Q(filiale=""))
    sorted_types = sorted(list(query), key=lambda x: 0 if x.filiale else 1)

    doc_types = []
    seen_codes = set()
    for dt in sorted_types:
        if dt.code not in seen_codes:
            seen_codes.add(dt.code)
            doc_types.append(dt)

    best_type = ""
    best_score = 0.0

    for doc_type in doc_types:
        score = 0.0
        for keyword in doc_type.get_keyword_list():
            if keyword in content:
                score += 1.0

        clean_filename = (original_name or "").upper()
        if doc_type.code.upper() in clean_filename or doc_type.label.upper() in clean_filename:
            score += 3.0

        if doc_type.code == "passeport":
            if re.search(r"(^|\n)\s*P<", text or "", flags=re.IGNORECASE):
                score += 5.0
        elif doc_type.code == "piece_identite":
            if re.search(r"(CNI|IDENTITE|IDENTITY|NATIONALID)", compact_content):
                score += 1.5

        if score >= doc_type.min_score and score > best_score:
            best_score = score
            best_type = doc_type.code

    return best_type


def extraction_quality_warnings(text, fields=None):
    text = text or ""
    fields = fields or {}
    stripped = text.strip()
    warnings = []

    if not stripped:
        return ["Document non exploitable: aucun texte lisible n'a ete detecte."]

    useful_chars = sum(1 for char in stripped if char.isalnum())
    useful_ratio = useful_chars / max(len(stripped), 1)
    key_fields = {"nom", "prenom", "numero_document", "date_naissance", "date_expiration", "nationalite"}
    detected_key_fields = [field for field in key_fields if fields.get(field)]

    if len(stripped) < 60 and len(detected_key_fields) < 2:
        warnings.append("Document potentiellement non exploitable: le texte extrait est trop court pour fiabiliser l'analyse.")
    if useful_ratio < 0.35 and len(detected_key_fields) < 3:
        warnings.append("Qualite du document a verifier: l'OCR contient trop peu de caracteres lisibles.")
    if len(detected_key_fields) == 0:
        warnings.append("Document non exploitable: aucun champ d'identite standard n'a ete reconnu.")
    elif len(detected_key_fields) < 2:
        warnings.append("Qualite insuffisante: trop peu de champs d'identite ont ete reconnus automatiquement.")

    return warnings


def _apply_detection_metadata(result, original_name="", filiale=None):
    fields = result.get("fields") or {}
    text = result.get("text") or ""
    result["detected_document_type"] = detect_document_type(text, original_name or result.get("filename", ""), fields, filiale)

    existing_warnings = list(result.get("warnings") or [])
    for warning in extraction_quality_warnings(text, fields):
        if warning not in existing_warnings:
            existing_warnings.append(warning)
    result["warnings"] = existing_warnings
    return result


def _all_dates(text):
    return [_clean_value(match.group(0)) for match in re.finditer(ANY_DATE_PATTERN, text or "", flags=re.IGNORECASE)]


def _uppercase_candidate(line):
    value = re.sub(r"[^A-ZÀ-Ÿ' -]", " ", (line or "").upper())
    value = _clean_value(value)
    if len(value) < 2 or len(value) > 35:
        return ""
    words = [word for word in value.split() if word]
    if not words or len(words) > 3 or any(len(word) < 3 for word in words):
        return ""
    if len(words) == 2 and len(words[1]) <= 2:
        value = words[0]
    rejected = (
        "REPUBLIQUE",
        "SENEGAL",
        "PASSPORT",
        "PASSEPORT",
        "NATIONALITE",
        "NATIONALITY",
        "DATE",
        "LIEU",
        "PLACE",
        "MINT",
        "DGP",
        "PAGE",
        "PAGES",
        "DES",
        "ETATS",
        "ECONOMIQUE",
        "SEN",
        "NIN",
        "PASSEPO",
        "ASSEPON",
        "AOSTT",
        "AOATT",
        "RIS",
        "AGEN",
        "PEE",
        "REM",
        "HORS",
        "CER",
        "POTE",
    )
    if any(word in value for word in rejected):
        return ""
    if not re.search(r"[AEIOUYÀ-Ÿ]", value):
        return ""
    return value


def _nationality_value(text):
    for label_pattern in [r"\bnationalite\b", r"\bnationality\b"]:
        match = re.search(label_pattern, text or "", flags=re.IGNORECASE)
        if not match:
            continue
        window = (text or "")[match.end():match.end() + 220]
        value_match = re.search(rf"\n\s*([A-ZÀ-Ÿ][A-ZÀ-Ÿ \t'-]{{3,}}?)\s+({ANY_DATE_PATTERN})", window, flags=re.IGNORECASE)
        if value_match:
            return _clean_value(value_match.group(1))

    for value in ("SENEGALAISE", "BENINOISE", "BENIN", "IVOIRIENNE", "BURKINABE", "MALIENNE", "TOGOLAISE", "NIGERIENNE"):
        if re.search(rf"\b{value}\b", text or "", flags=re.IGNORECASE):
            return value
    return ""


def _passport_heuristic_fields(text):
    fields = {}
    normalized = text or ""
    upper = normalized.upper()

    number_matches = re.findall(r"\bP\s*SEN\s*[:\-]?\s*([A-Z0-9 ]{6,14})", upper)
    if number_matches:
        candidates = [re.sub(r"\s+", "", value) for value in number_matches]
        candidates = [value for value in candidates if sum(ch.isdigit() for ch in value) >= 4]
        if candidates:
            fields["numero_document"] = candidates[-1]

    if "SENEGALAISE" in upper:
        fields["nationalite"] = "SENEGALAISE"
    if "REPUBLIQUE DU SENEGAL" in upper or "REPUBLIC OF SENEGAL" in upper:
        fields["pays_delivrance"] = "SENEGAL"
    elif "REPUBLIQUE DU BENIN" in upper or "REPUBLIC OF BENIN" in upper:
        fields["pays_delivrance"] = "BENIN"

    dates = []
    for date in _all_dates(normalized):
        normalized_date = re.sub(r"\s+", " ", date.upper())
        normalized_date = re.sub(r"\s*/\s*", "/", normalized_date)
        existing = [re.sub(r"\s*/\s*", "/", re.sub(r"\s+", " ", item.upper())) for item in dates]
        if normalized_date not in existing:
            dates.append(date)
    if dates:
        fields["date_naissance"] = dates[0]
        if len(dates) >= 2:
            fields["date_expiration"] = dates[-1]
        else:
            partial_expiry = re.search(rf"(?:{MONTH_PATTERN})\s*\/?\s*(?:{MONTH_PATTERN})?\s+20\d{{2}}", normalized, flags=re.IGNORECASE)
            if partial_expiry:
                fields["date_expiration"] = _clean_value(partial_expiry.group(0))

    place_match = re.search(r"\b([A-ZÀ-Ÿ]{3,}(?:[ /-][A-ZÀ-Ÿ]{2,})?)\s+MINT\s*[\/I]?\s*DGP", upper)
    if place_match:
        fields["lieu_naissance"] = _clean_value(place_match.group(1))
    else:
        place_match = re.search(r"\n\s*([A-ZÀ-Ÿ]{3,}(?:[ -][A-ZÀ-Ÿ]{2,})?)\s*\n\s*(?:HEIGHT|COULEUR)", upper)
        if place_match:
            fields["lieu_naissance"] = _clean_value(place_match.group(1))

    lines = _lines(normalized)
    best_pair = None
    for index, line in enumerate(lines):
        if re.search(r"\bSENEGALAISE\b", line, flags=re.IGNORECASE):
            candidates = []
            for previous in lines[max(0, index - 10):index]:
                candidate = _uppercase_candidate(previous)
                if candidate and candidate not in candidates:
                    candidates.append(candidate)
            if len(candidates) >= 2:
                pair = (candidates[-2], candidates[-1])
                if len(pair[0].replace(" ", "")) < 4:
                    continue
                if not best_pair or sum(len(value) for value in pair) < sum(len(value) for value in best_pair):
                    best_pair = pair
    if best_pair:
        nom = best_pair[0]
        if nom.endswith("F") and f"{nom[:-1]}P" in upper:
            nom = f"{nom[:-1]}P"
        fields["nom"] = nom
        fields["prenom"] = best_pair[1]

    return {key: value for key, value in fields.items() if value}


def parse_identity_fields(text):
    normalized = text or ""
    mrz_fields = _mrz_identity_fields(normalized)
    passport_fields = _passport_heuristic_fields(normalized)
    birth_date_patterns = [
        r"date\s+de\s+naissance",
        r"birth\s+date",
        r"date\s+of\s+birth",
        r"\bdob\b",
    ]
    expiry_date_patterns = [
        r"date\s+d[' ]?expiration",
        r"dated\s+expiration",
        r"expiration",
        r"expiry",
        r"expire",
        r"validite",
        r"valid\s+until",
    ]
    fields = {
        "prenom": mrz_fields.get("prenom", "") or _next_value_after_label(
            normalized,
            [r"\bprenoms?\b", r"\bgiven\s+names?\b", r"\bfirst\s+names?\b"],
        ) or _first_match(
            [
                r"^\s*(?:prenom|prenoms|given names?|first name)\s*[:\/\-]?\s*([A-Z][A-Z \t'._-]{2,})$",
                r"\b(?:prenom|prenoms|given names?|first name)\s*[:\/\-]?\s*([A-Z][A-Z \t'._-]{2,})",
            ],
            normalized,
        ) or passport_fields.get("prenom", ""),
        "nom": mrz_fields.get("nom", "") or _next_value_after_label(
            normalized,
            [r"\bdenomination\s+sociale\b", r"\braison\s+sociale\b", r"\bnom\s+de\s+l[' ]?entreprise\b", r"\bnom\s+social\b", r"\bnom\b", r"\bnorn\b", r"\bsurname\b", r"\bsumame\b"],
        ) or _first_match(
            [
                r"\b(?:denomination\s+sociale|raison\s+sociale|nom\s+de\s+l[' ]?entreprise|nom\s+social)\s*[:\/\-]?\s*([A-Z0-9][A-Z0-9 \t'._-]{2,})",
                r"^\s*(?:nom|norn|surname|sumame)\s*[:\/\-]?\s*([A-Z][A-Z \t'._-]{2,})$",
                r"\b(?:nom|norn|surname|sumame)\s*[:\/\-]?\s*([A-Z][A-Z \t'._-]{2,})",
            ],
            normalized,
        ) or passport_fields.get("nom", ""),
        "numero_document": mrz_fields.get("numero_document", "") or _first_match(
            [
                r"\b(?:rcs|rccm|registre\s+du\s+commerce|n°\s+rccm|rc)\s*[:\-]?\s*([A-Z0-9][A-Z0-9 \t\-\/._]{4,})",
                r"\b(?:numero\s+de\s+carte|card\s+number)\s*[:\-]?\s*([A-Z0-9][A-Z0-9 \t\-\/]{4,})",
                r"\b(?:n[°o]\s*passeport|passport\s*(?:no|number))\s*[:\-]?\s*([A-Z0-9][A-Z0-9 \t\-\/]{4,})",
                r"\b(?:cni|numero|num|no\b|n[°o]\b)\s*[:\-]?\s*([A-Z0-9][A-Z0-9 \t\-\/]{4,})",
            ],
            normalized,
        ) or passport_fields.get("numero_document", ""),
        "numero_identification_nationale": _first_match(
            [
                r"\b(?:nif|numero\s+fiscal|identification\s+fiscale|identifiant\s+fiscal|num[eé]ro\s+d[' ]?identification\s+fiscale|fiscal\s+id(?:entification)?\s*(?:number|no)?|matricule\s+fiscal).*?([A-Z0-9][A-Z0-9 \t\-\/._]{5,})",
                r"\b(?:numero\s+personnel\s+d[' ]?identification|npi|e[idlD]\s+number|numero\s+d[' ]?identification\s+nationale|national\s+identification\s+number|nin).*?([0-9][0-9 \t]{7,})",
                r"\b(?:personal\s+no|personal\s+number|n[°o]\s+personnel)\s*[:\/\-]?\s*([0-9][0-9 \t]{5,})",
            ],
            normalized,
        ) or mrz_fields.get("numero_identification_nationale", ""),
        "date_naissance": mrz_fields.get("date_naissance", "") or _first_date_near_label(normalized, birth_date_patterns) or _first_match(
            [
                rf"\b(?:date de naissance|naissance|birth date|date of birth|dob)\s*[:\-]?\s*({ANY_DATE_PATTERN})",
            ],
            normalized,
        ) or passport_fields.get("date_naissance", ""),
        "lieu_naissance": _next_value_after_label(
            normalized,
            [r"lieu\s+de\s+na.{0,10}sance", r"place\s+of\s+birth"],
            skip_patterns=[r"^sexe\b", r"^[mf]$", r"^taille\b"],
        ) or passport_fields.get("lieu_naissance", ""),
        "sexe": mrz_fields.get("sexe", "") or _sex_near_label(normalized),
        "date_expiration": mrz_fields.get("date_expiration", "") or _first_date_near_label(normalized, expiry_date_patterns) or _first_match(
            [
                rf"\b(?:date d'expiration|expiration|expiry|expire|validite|valid until)\s*[:\-]?\s*({ANY_DATE_PATTERN})",
            ],
            normalized,
        ) or passport_fields.get("date_expiration", ""),
        "adresse": _next_value_after_label(
            normalized,
            [r"adresse\s+sociale\b", r"si[eè]ge\s+social\b", r"adresse\s+du\s+si[eè]ge\b", r"adresse\s+du\s+dom[il1c]{2,}le", r"adresse\s+du\s+dorm", r"\badresse\b", r"\baddress\b"],
        ),
        "pays_naissance": _next_value_after_label(
            normalized,
            [r"pays\s+de\s+naissance", r"country\s+of\s+birth"],
        ) or _first_match(
            [
                r"\b(?:pays de naissance|country of birth)\s*[:\-]?\s*([A-Z][A-Z \t'._-]{2,})",
            ],
            normalized,
        ),
        "pays_delivrance": mrz_fields.get("pays_delivrance", "") or passport_fields.get("pays_delivrance", "") or _next_value_after_label(
            normalized,
            [r"pays\s+de\s+delivrance", r"pays\s+d[' ]?emission", r"issuing\s+country", r"country\s+of\s+issue"],
        ),
        "nationalite": mrz_fields.get("nationalite", "") or _nationality_value(normalized) or _value_before_date(_next_value_after_label(
            normalized,
            [r"\bnationalite\b", r"\bnationality\b"],
            max_lines=3,
        )) or _first_match(
            [
                r"\b(?:nationalite|nationality)\s*[:\-]?\s*([A-Z][A-Z \t'._-]{2,})",
            ],
            normalized,
        ) or passport_fields.get("nationalite", ""),
        "origine_revenu": _next_value_after_label(
            normalized,
            [r"origine\s+(?:des\s+)?revenus?", r"source\s+of\s+(?:funds|income)", r"income\s+source"],
        ) or _first_match(
            [
                r"\b(?:origine des revenus?|origine revenu|source of funds|source of income|income source)\s*[:\-]?\s*([A-Z][A-Z \t'._-]{2,})",
            ],
            normalized,
        ),
    }
                                                                             
                                                                                 
    def _document_number_or_empty(value):
        value = _clean_value(value)
        return value if sum(ch.isdigit() for ch in value) >= 3 else ""

    numero_document = _document_number_or_empty(fields.get("numero_document", ""))
    if not numero_document:
        numero_document = _document_number_or_empty(_next_value_after_label(
            normalized,
            [
                r"n[°o]?\s*de\s+la\s+carte\s+d[' ]?identit\S*",
                r"numero\s+de\s+(?:la\s+)?carte\s*\S*",
                r"card\s+number",
            ],
        ))
    if numero_document:
        fields["numero_document"] = numero_document
    else:
        fields.pop("numero_document", None)

                                                                              
                                                                            
    delivery_expiry = re.search(
        rf"d[ée]livrance[^\n]*expir[^\n]*\n[^\n]*?({ANY_DATE_PATTERN})\s+({ANY_DATE_PATTERN})",
        normalized,
        flags=re.IGNORECASE,
    )
    if delivery_expiry:
        fields["date_expiration"] = _clean_value(delivery_expiry.group(2))

    lieu_naissance = fields.get("lieu_naissance", "")
    split_lieu = re.match(r"^([MFX])\s+(.+)$", lieu_naissance, flags=re.IGNORECASE)
    if split_lieu:
        fields["sexe"] = fields.get("sexe") or split_lieu.group(1).upper()
        fields["lieu_naissance"] = _clean_value(split_lieu.group(2))

    sexe = (fields.get("sexe") or "").strip().upper()
    if sexe.startswith("M"):
        fields["sexe"] = "M"
    elif sexe.startswith("F"):
        fields["sexe"] = "F"
    elif sexe.startswith("X"):
        fields["sexe"] = "X"

    return {key: value for key, value in fields.items() if value}


                                                                         
                                                                    
                                                                       
                                        
                                                                         
_RAPIDOCR_LOCK = threading.Lock()
_RAPIDOCR_ENGINE = None
_RAPIDOCR_ERROR = None


def _get_rapidocr_engine():
    """Initialise RapidOCR une seule fois (thread-safe). Retourne None si
    la librairie n'est pas installee ou si l'initialisation echoue."""
    global _RAPIDOCR_ENGINE, _RAPIDOCR_ERROR
    if _RAPIDOCR_ENGINE is not None or _RAPIDOCR_ERROR is not None:
        return _RAPIDOCR_ENGINE
    with _RAPIDOCR_LOCK:
        if _RAPIDOCR_ENGINE is None and _RAPIDOCR_ERROR is None:
            try:
                from rapidocr import RapidOCR
                _RAPIDOCR_ENGINE = RapidOCR(params={"Rec.lang_type": "fr"})
            except Exception as exc:                                              
                _RAPIDOCR_ERROR = str(exc)
    return _RAPIDOCR_ENGINE


def _rapidocr_reading_order(boxes, txts, scores, min_score=0.5):
    """Reconstruit l'ordre de lecture (haut -> bas, gauche -> droite) a partir
    des boites detectees, en regroupant les fragments d'une meme ligne."""
    items = []
    for box, txt, score in zip(boxes, txts, scores):
        if not txt or score < min_score:
            continue
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        top, bottom = min(ys), max(ys)
        items.append({"center": (top + bottom) / 2.0, "height": max(bottom - top, 1), "left": min(xs), "text": txt.strip()})

    items.sort(key=lambda item: item["center"])
    lines = []
    for item in items:
        placed = False
        for line in lines:
            tolerance = max(item["height"], line["height"]) * 0.6
            if abs(item["center"] - line["center"]) <= tolerance:
                line["parts"].append((item["left"], item["text"]))
                placed = True
                break
        if not placed:
            lines.append({"center": item["center"], "height": item["height"], "parts": [(item["left"], item["text"])]})

    return "\n".join(
        " ".join(text for _, text in sorted(line["parts"], key=lambda part: part[0]))
        for line in lines
    )


def _rapidocr_scan(image, min_score=0.5):
    """OCR d'une image PIL avec RapidOCR. Retourne (texte, ratio_vertical) ou
    None si le moteur est indisponible. Un ratio_vertical eleve signifie que
    les boites de texte detectees sont majoritairement verticales : l'image
    est probablement tournee de 90 degres."""
    engine = _get_rapidocr_engine()
    if engine is None:
        return None
    try:
        import numpy as np
        result = engine(np.array(image.convert("RGB")))
    except Exception:
        return None
    if result is None or not getattr(result, "txts", None):
        return "", 0.0
    boxes = result.boxes if result.boxes is not None else []
    scores = result.scores if result.scores is not None else [1.0] * len(result.txts)

    vertical = horizontal = 0
    for box, txt in zip(boxes, result.txts):
        if len((txt or "").strip()) < 3:
            continue
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        if height > width * 1.3:
            vertical += 1
        else:
            horizontal += 1
    vertical_ratio = vertical / max(vertical + horizontal, 1)

    text = _rapidocr_reading_order(boxes, result.txts, scores, min_score=min_score)
    return text, vertical_ratio


def _rapidocr_text(image, min_score=0.5):
    scan = _rapidocr_scan(image, min_score=min_score)
    if scan is None:
        return None
    return scan[0]


def _rapidocr_variants(image):
    """Essaie RapidOCR sur l'image puis sur les rotations 90/270 et retourne le
    meilleur texte. Une orientation dont les boites sont majoritairement
    verticales est consideree comme tournee : pas d'arret anticipe dessus.
    Retourne None si le moteur est indisponible."""
    best_text = ""
    best_field_count = -1
    for angle in (0, 90, 270):
        oriented = image if angle == 0 else image.rotate(angle, expand=True)
        scan = _rapidocr_scan(oriented)
        if scan is None:
            return None
        text, vertical_ratio = scan
        well_oriented = vertical_ratio <= 0.5
        if text and well_oriented and _has_enough_core_fields(text):
            return text
        field_count = len(parse_identity_fields(text)) if text else 0
        if not well_oriented:
            field_count -= 2                                       
        if field_count > best_field_count or (field_count == best_field_count and len(text) > len(best_text)):
            best_text = text
            best_field_count = field_count
    return best_text


def _configure_tesseract(pytesseract):
    candidates = [
        os.environ.get("TESSERACT_CMD"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Tesseract-OCR", "tesseract.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Tesseract-OCR", "tesseract.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return candidate
    return ""


def _prepare_image_for_ocr(image):
    from PIL import ImageOps, ImageFilter

    prepared = ImageOps.grayscale(image)
    prepared = ImageOps.autocontrast(prepared)
    width, height = prepared.size
    if max(width, height) < 1800:
        prepared = prepared.resize((width * 2, height * 2))
    return prepared.filter(ImageFilter.SHARPEN)


def _ocr_image(image, psm=3):
    import pytesseract

    _configure_tesseract(pytesseract)
    prepared = _prepare_image_for_ocr(image)
    config = f"--oem 3 --psm {psm}"
    try:
        return pytesseract.image_to_string(prepared, lang=TESSERACT_LANG, config=config)
    except Exception:
        return pytesseract.image_to_string(prepared, lang="eng", config=config)


def _ocr_image_variants(image):
    """OCR d'une image : RapidOCR d'abord (rapide et precis), puis repli sur
    le pipeline Tesseract multi-passes si les champs coeur restent absents."""
    rapid_text = _rapidocr_variants(image)
    if rapid_text and _has_enough_core_fields(rapid_text):
        return rapid_text

    tesseract_text = _tesseract_image_variants(image)
    if rapid_text and tesseract_text:
        return f"{rapid_text}\n{tesseract_text}"
    return rapid_text or tesseract_text


def _tesseract_image_variants(image):
    """OCR Tesseract multi-passes avec arret anticipe : on s'arrete des que le
    texte cumule contient les champs coeur (nom/numero/dates), au lieu de faire
    systematiquement toutes les orientations/regions/PSM (jusqu'a 27 passes)."""
    try:
        import pytesseract              
    except ImportError:
        return ""
    orientations = [
        image,
        image.rotate(90, expand=True),
        image.rotate(270, expand=True),
    ]
    texts = []
    seen = set()
    for oriented in orientations:
        width, height = oriented.size
        regions = [
            oriented,
            oriented.crop((0, int(height * 0.45), width, height)),
            oriented.crop((int(width * 0.15), int(height * 0.40), width, height)),
        ]
        for region in regions:
            for psm in (3, 6, 11):
                text = _ocr_image(region, psm=psm).strip()
                key = re.sub(r"\s+", " ", text)
                if text and key not in seen:
                    seen.add(key)
                    texts.append(text)
                    if _has_enough_core_fields("\n".join(texts)):
                        return "\n".join(texts)
    return "\n".join(texts)


def _extract_text_from_image(path):
    try:
        from PIL import Image
    except ImportError:
        return "", [
            "OCR image indisponible: installez Pillow, rapidocr et onnxruntime sur le serveur."
        ]

    try:
        with Image.open(path) as image:
            text = _ocr_image_variants(image)
        warnings = []
        if not (text or "").strip() and _get_rapidocr_engine() is None:
            warnings.append(
                "Moteur OCR principal indisponible (rapidocr/onnxruntime non installes) "
                "et le repli Tesseract n'a rien extrait."
            )
        return text, warnings
    except Exception as exc:
        return "", [f"OCR image impossible: {exc}"]


def _extract_text_from_pdf(path):
    warnings = []
    text_layer_parts = []
    ocr_parts = []

    try:
        from pypdf import PdfReader
    except ImportError:
        PdfReader = None

    if PdfReader:
        try:
            reader = PdfReader(path)
            for page in reader.pages[:5]:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_layer_parts.append(page_text)
        except Exception as exc:
            warnings.append(f"Lecture PDF texte impossible: {exc}")

    if text_layer_parts:
        text_layer = "\n".join(text_layer_parts)
        if _has_enough_core_fields(text_layer):
            return text_layer, warnings

    try:
        import fitz
        from PIL import Image
    except ImportError:
        if text_layer_parts:
            return "\n".join(text_layer_parts), warnings
        warnings.append("PDF scanne detecte, mais OCR PDF indisponible: installez PyMuPDF, Pillow et pytesseract.")
        return "", warnings

    try:
        document = fitz.open(path)
        matrix = fitz.Matrix(2.5, 2.5)
        rendered_images = []
        basic_ocr_parts = []
        for page_index in range(min(document.page_count, 5)):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.open(BytesIO(pixmap.tobytes("png")))
            rendered_images.append(image)
            page_text = _rapidocr_variants(image)
            if not page_text:
                page_text = _ocr_image(image, psm=3)
            basic_ocr_parts.append(page_text)

        basic_text = "\n".join(basic_ocr_parts + text_layer_parts)
        if _has_enough_core_fields(basic_text):
            return basic_text, warnings

        for image in rendered_images:
            ocr_parts.append(_ocr_image_variants(image))
        return "\n".join(ocr_parts + text_layer_parts), warnings
    except Exception as exc:
        warnings.append(f"OCR PDF impossible: {exc}")
        return "\n".join(text_layer_parts), warnings


def _extract_pdf_pages_with_text_layer(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return [], ["Lecture PDF page par page indisponible: installez pypdf."]

    warnings = []
    try:
        reader = PdfReader(path)
        page_texts = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                page_texts.append({"page_number": index, "text": page.extract_text() or ""})
            except Exception as exc:
                warnings.append(f"Lecture texte impossible page {index}: {exc}")
                page_texts.append({"page_number": index, "text": ""})
        return page_texts, warnings
    except Exception as exc:
        return [], [f"Lecture PDF page par page impossible: {exc}"]


def _extract_pdf_pages_with_ocr(path):
    warnings = []
    text_pages = []

    try:
        import fitz
        from PIL import Image
    except ImportError:
        return [], ["OCR PDF page par page indisponible: installez PyMuPDF, Pillow et pytesseract."]

    try:
        document = fitz.open(path)
        matrix = fitz.Matrix(2.5, 2.5)
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.open(BytesIO(pixmap.tobytes("png")))
            text_pages.append({"page_number": page_index + 1, "text": _ocr_image_variants(image)})
        return text_pages, warnings
    except Exception as exc:
        return [], [f"OCR PDF page par page impossible: {exc}"]


def extract_pdf_grouped_documents(path, original_name="", pages_per_document=1, filiale=None):
    pages_per_document = max(int(pages_per_document or 1), 1)
    page_texts, warnings = _extract_pdf_pages_with_text_layer(path)

    if not any((page.get("text") or "").strip() for page in page_texts):
        ocr_pages, ocr_warnings = _extract_pdf_pages_with_ocr(path)
        if ocr_pages:
            page_texts = ocr_pages
        warnings.extend(ocr_warnings)

    if not page_texts:
        return [_apply_detection_metadata({
            "filename": original_name or os.path.basename(path),
            "extension": ".pdf",
            "text": "",
            "fields": {},
            "warnings": warnings + ["Aucune page exploitable n'a ete extraite du PDF groupe."],
            "supported": True,
            "page_number": None,
            "page_range": "",
        }, original_name, filiale)]

    grouped_results = []
    for start in range(0, len(page_texts), pages_per_document):
        group = page_texts[start:start + pages_per_document]
        page_numbers = [page["page_number"] for page in group]
        text = "\n".join(page.get("text") or "" for page in group)
        page_range = str(page_numbers[0]) if len(page_numbers) == 1 else f"{page_numbers[0]}-{page_numbers[-1]}"
        group_warnings = list(warnings)
        if not text.strip():
            group_warnings.append("Aucun texte exploitable n'a ete extrait pour ce document.")

        grouped_results.append(_apply_detection_metadata({
            "filename": original_name or os.path.basename(path),
            "extension": ".pdf",
            "text": text,
            "fields": parse_identity_fields(text) if text.strip() else {},
            "warnings": group_warnings,
            "supported": True,
            "page_number": page_numbers[0],
            "page_range": page_range,
        }, original_name, filiale))

    return grouped_results


def extract_document_data(path, original_name="", filiale=None):
    extension = os.path.splitext(original_name or path)[1].lower()
    result = {
        "filename": original_name or os.path.basename(path),
        "extension": extension,
        "text": "",
        "fields": {},
        "warnings": [],
        "supported": extension in SUPPORTED_EXTENSIONS,
    }

    if not result["supported"]:
        result["warnings"].append("Format non pris en charge. Utilisez PDF, PNG, JPG, TIFF, BMP ou TXT.")
        return result

    if extension == ".txt":
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                result["text"] = handle.read()
        except Exception as exc:
            result["warnings"].append(f"Lecture du fichier texte impossible: {exc}")
    elif extension == ".pdf":
        result["text"], warnings = _extract_text_from_pdf(path)
        result["warnings"].extend(warnings)
    elif extension in IMAGE_EXTENSIONS:
        result["text"], warnings = _extract_text_from_image(path)
        result["warnings"].extend(warnings)

    if result["text"].strip():
        result["fields"] = parse_identity_fields(result["text"])
    else:
        result["warnings"].append("Aucun texte exploitable n'a ete extrait du document.")

    return _apply_detection_metadata(result, original_name, filiale)


def learn_document_keywords(document_text, document_type_code, filiale=None):
    if not document_text or not document_type_code:
        return

    from kyc.models import KycDocumentType

    try:
        doc_type = KycDocumentType.objects.get(code=document_type_code, filiale=filiale or "")
    except KycDocumentType.DoesNotExist:
        try:
            doc_type = KycDocumentType.objects.get(code=document_type_code, filiale="")
        except KycDocumentType.DoesNotExist:
            return

    text = re.sub(r"[^A-ZÀ-Ÿa-zà-ÿ\s]", " ", document_text)
    words = text.upper().split()

    STOPWORDS = {
        "LE", "LA", "LES", "UN", "UNE", "DES", "DE", "DU", "D'", "EN", "AU", "AUX", "PAR", "POUR", 
        "SUR", "AVEC", "DANS", "SANS", "SOUS", "ET", "OU", "MAIS", "DONC", "OR", "NI", "CAR", 
        "CE", "CET", "CETTE", "CES", "MON", "TON", "SON", "MA", "TA", "SA", "MES", "TES", "SES",
        "THE", "AND", "OF", "IN", "TO", "FOR", "WITH", "ON", "AT", "BY", "AN", "THIS", "THAT",
        "DATE", "LIEU", "NOM", "PRENOM", "PRENOMS", "SEXE", "TAILLE", "ADRESSE", "SENEGAL", 
        "BENIN", "MALI", "TOGO", "NIGER", "REPUBLIQUE", "MINISTERE", "CARTE", "CARD"
    }

    candidate_words = []
    for word in words:
        word = word.strip()
        if len(word) >= 4 and word not in STOPWORDS and not word.isdigit():
            candidate_words.append(word)

    from collections import Counter
    word_counts = Counter(candidate_words)
    top_words = [word for word, count in word_counts.most_common(5)]

    if not top_words:
        return

    current_keywords = doc_type.get_keyword_list()
    added_any = False
    for word in top_words:
        if word not in current_keywords:
            current_keywords.append(word)
            added_any = True

    if added_any:
        doc_type.keywords = ", ".join(current_keywords)
        doc_type.save()
