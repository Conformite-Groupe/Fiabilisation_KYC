import csv
import os
import re
import sys
import logging
from datetime import datetime
import argparse

try:
    import pyodbc  # type: ignore
except Exception:
    pyodbc = None

# =====================================================
# 1. PARAMETRES GLOBAUX
# =====================================================
CHEMIN_BASE = os.environ.get(
    "KYC_DATA_DIR",
    r"C:\Fiabilisation KYC\Python\data",
)
ANOMALIES_PATTERN = os.environ.get(
    "KYC_ANOMALIES_PATTERN",
    os.path.join(CHEMIN_BASE, "anomalies_{code}.csv"),
)
SCORING_PATTERN = os.environ.get(
    "KYC_SCORING_PATTERN",
    os.path.join(CHEMIN_BASE, "scoring_{code}.csv"),
)
SUIVI_PATTERN = os.environ.get(
    "KYC_SUIVI_PATTERN",
    os.path.join(CHEMIN_BASE, "suivi_fiabilisation_{code}.csv"),
)

DELIMITEUR = ";"
BULK_SIZE_TAUX_FILIALE = 500
BULK_SIZE_ANOMALIE = 5000
BULK_SIZE_DATEREV = 20000
LOG_STEP = 100000

# Tables MSSQL par defaut (Django default)
TABLE_ANOMALIE = os.environ.get("MSSQL_TABLE_ANOMALIE", "kyc_anomalie")
TABLE_DATEREV = os.environ.get("MSSQL_TABLE_DATEREV", "kyc_daterev")
TABLE_TAUX_FILIALE = os.environ.get("MSSQL_TABLE_TAUX_FILIALE", "kyc_tauxevolution_filiale")

# =====================================================
# 2. LOGGING
# =====================================================
def setup_logging():
    logger = logging.getLogger("KYC_Importer_MSSQL")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    if not logger.handlers:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        logger.addHandler(console)
    return logger

logger = setup_logging()

# =====================================================
# 3. UTILS
# =====================================================
def parse_date_multi(val):
    if not val or str(val).lower() in ("nan", "null", "", "none"):
        return None

    s = str(val).strip()
    if len(s) == 10:
        if s[4] == "-" and s[7] == "-":
            try:
                return datetime(int(s[0:4]), int(s[5:7]), int(s[8:10])).date()
            except ValueError:
                pass
        if s[2] == "/" and s[5] == "/":
            try:
                return datetime(int(s[6:10]), int(s[3:5]), int(s[0:2])).date()
            except ValueError:
                pass

    clean_val = re.sub(r"[^0-9/-]", "", s)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(clean_val, fmt).date()
        except ValueError:
            continue
    return None

def parse_taux(val):
    if not val or str(val).strip() == "":
        return 0.0
    try:
        return float(str(val).replace("%", "").replace(",", ".").strip())
    except ValueError:
        return 0.0

def normalize_header(name):
    return (name or "").strip().upper().replace("\ufeff", "")

def pick_value(row_norm, candidates):
    for col in candidates:
        val = row_norm.get(col, "")
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    if candidates:
        return (row_norm.get(candidates[0], "") or "").strip()
    return ""

try:
    import chardet  # type: ignore
except Exception:
    chardet = None

def detect_encoding(path):
    if chardet is None:
        return "utf-8-sig"
    try:
        with open(path, "rb") as f:
            raw = f.read(100000)
        enc = chardet.detect(raw).get("encoding")
        return enc or "utf-8-sig"
    except Exception:
        return "utf-8-sig"

def resolve_path(pattern, code):
    return pattern.format(code=code)

def build_filiales_codes(cli_filiales=None):
    if cli_filiales:
        parts = [p.strip() for p in cli_filiales.replace(";", ",").split(",")]
        return [p for p in parts if p]

    override = os.environ.get("KYC_FILIALES")
    if override:
        parts = [p.strip() for p in override.replace(";", ",").split(",")]
        return [p for p in parts if p]

    # fallback manuel si rien n'est fourni
    return ["SN", "CI", "BF", "TG", "NE"]

# =====================================================
# 4. MSSQL
# =====================================================
def get_conn():
    if pyodbc is None:
        raise RuntimeError("pyodbc n'est pas installe. Installe-le: pip install pyodbc")

    driver = os.environ.get("MSSQL_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.environ.get("MSSQL_SERVER", "")
    database = os.environ.get("MSSQL_DATABASE", "")
    user = os.environ.get("MSSQL_USER", "")
    password = os.environ.get("MSSQL_PASSWORD", "")
    trusted = os.environ.get("MSSQL_TRUSTED", "false").lower() in ("1", "true", "yes")

    if not server or not database:
        raise RuntimeError("MSSQL_SERVER et MSSQL_DATABASE sont requis.")

    if trusted:
        conn_str = (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;"
        )
    else:
        if not user or not password:
            raise RuntimeError("MSSQL_USER et MSSQL_PASSWORD sont requis.")
        conn_str = (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={user};PWD={password};"
        )

    return pyodbc.connect(conn_str)

def exec_delete_by_filiale(conn, table, filiale_col, filiale_val):
    sql = f"DELETE FROM {table} WHERE {filiale_col} = ?"
    cur = conn.cursor()
    cur.execute(sql, (filiale_val,))
    conn.commit()
    return cur.rowcount

def bulk_insert(conn, table, columns, rows, batch_size):
    if not rows:
        return 0
    placeholders = ",".join(["?"] * len(columns))
    col_list = ",".join(columns)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
    cur = conn.cursor()
    cur.fast_executemany = True
    inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            cur.executemany(sql, batch)
            conn.commit()
            inserted += len(batch)
        except Exception as e:
            logger.error(f"bulk insert failed on {table}: {e}")
            for r in batch:
                try:
                    cur.execute(sql, r)
                    inserted += 1
                except Exception as row_e:
                    logger.error(f"row insert failed on {table}: {row_e}")
            conn.commit()
    return inserted

# =====================================================
# 5. IMPORT ANOMALIES
# =====================================================
def import_anomalies(conn, filiales):
    logger.info("START ANOMALIES")
    mapping = {
        "AGENCE": ["AGENCE", "AG", "CODE_AGENCE"],
        "LIB_AGENCE": ["AGENCELIB", "LIB_AGENCE"],
        "EXPL": ["EXPL"],
        "CLIENT": ["CLIENT"],
        "ANOMALIE_AGE": ["ANOMALIE_AGE"],
        "ANOMALIE_DATE_EER": ["ANOMALIE_DATE_EER"],
        "ANOMALIE_CIN": ["ANOMALIE_CIN"],
        "PPE": ["PPE"],
    }
    required_keys = [
        "AGENCE",
        "EXPL",
        "CLIENT",
        "ANOMALIE_AGE",
        "ANOMALIE_DATE_EER",
        "ANOMALIE_CIN",
        "PPE",
    ]
    optional_keys = ["LIB_AGENCE"]

    for code in filiales:
        nom_filiale_complet = f"BOA {code}"
        fichier = resolve_path(ANOMALIES_PATTERN, code)

        if not os.path.exists(fichier):
            logger.warning(f"missing anomalies file: {fichier}")
            continue

        deleted = exec_delete_by_filiale(conn, TABLE_ANOMALIE, "FILIALE", nom_filiale_complet)
        logger.info(f"cleaned {deleted} rows for {nom_filiale_complet}")

        buffer = []
        inserted_for_filiale = 0

        encodings = [detect_encoding(fichier), "utf-8-sig", "latin-1", "cp1252"]
        seen = set()
        encodings = [e for e in encodings if not (e in seen or seen.add(e))]

        for enc in encodings:
            try:
                with open(fichier, "r", encoding=enc, errors="replace") as f:
                    reader = csv.DictReader(f, delimiter=DELIMITEUR, skipinitialspace=True)
                    if reader.fieldnames:
                        reader.fieldnames = [normalize_header(fn) for fn in reader.fieldnames]
                        logger.debug(f"[{code}] anomalies encoding={enc} headers={reader.fieldnames}")
                    else:
                        logger.error(f"empty headers for {code}")
                        break

                    header_set = set(reader.fieldnames)
                    missing = []
                    for key in required_keys:
                        candidates = [normalize_header(c) for c in mapping[key]]
                        if not any(c in header_set for c in candidates):
                            missing.append(key)
                    if missing:
                        logger.error(f"missing required columns for {code}: {missing}")
                        break

                    for key in optional_keys:
                        candidates = [normalize_header(c) for c in mapping[key]]
                        if not any(c in header_set for c in candidates):
                            logger.warning(f"missing optional column {key} for {code}")

                    for line_num, row in enumerate(reader, start=1):
                        try:
                            row_norm = {normalize_header(k): (v or "") for k, v in row.items()}

                            ag = pick_value(row_norm, [normalize_header(c) for c in mapping["AGENCE"]])
                            if not ag:
                                continue

                            def norm_num(val):
                                return (val or "").replace(",", ".").strip()

                            values = (
                                nom_filiale_complet,
                                ag,
                                pick_value(row_norm, [normalize_header(c) for c in mapping["LIB_AGENCE"]]),
                                pick_value(row_norm, [normalize_header(c) for c in mapping["EXPL"]]),
                                pick_value(row_norm, [normalize_header(c) for c in mapping["CLIENT"]]),
                                norm_num(pick_value(row_norm, [normalize_header(c) for c in mapping["ANOMALIE_AGE"]])),
                                norm_num(pick_value(row_norm, [normalize_header(c) for c in mapping["ANOMALIE_DATE_EER"]])),
                                norm_num(pick_value(row_norm, [normalize_header(c) for c in mapping["ANOMALIE_CIN"]])),
                                norm_num(pick_value(row_norm, [normalize_header(c) for c in mapping["PPE"]])),
                            )
                            buffer.append(values)

                            if len(buffer) >= BULK_SIZE_ANOMALIE:
                                inserted_for_filiale += bulk_insert(
                                    conn,
                                    TABLE_ANOMALIE,
                                    [
                                        "FILIALE",
                                        "AGENCE",
                                        "LIB_AGENCE",
                                        "EXPL",
                                        "CLIENT",
                                        "ANOMALIE_AGE",
                                        "ANOMALIE_DATE_EER",
                                        "ANOMALIE_CIN",
                                        "PPE",
                                    ],
                                    buffer,
                                    BULK_SIZE_ANOMALIE,
                                )
                                buffer.clear()
                        except Exception as e:
                            if line_num % 10000 == 0:
                                logger.error(f"line {line_num} error: {e}")
                            continue

                    if buffer:
                        inserted_for_filiale += bulk_insert(
                            conn,
                            TABLE_ANOMALIE,
                            [
                                "FILIALE",
                                "AGENCE",
                                "LIB_AGENCE",
                                "EXPL",
                                "CLIENT",
                                "ANOMALIE_AGE",
                                "ANOMALIE_DATE_EER",
                                "ANOMALIE_CIN",
                                "PPE",
                            ],
                            buffer,
                            BULK_SIZE_ANOMALIE,
                        )

                logger.info(f"done {code}: {inserted_for_filiale} rows")
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.error(f"critical error on {code}: {e}")
                break

    logger.info("END ANOMALIES")

# =====================================================
# 6. IMPORT DATEREV
# =====================================================
def import_daterev(conn, filiales):
    total = 0
    logger.info("START DATEREV")
    mapping = {
        "AGENCE": ["AGENCE", "AG"],
        "LIB_AGENCE": ["AGENCELIB", "LIB_AGENCE"],
        "EXPL": ["EXPL"],
        "CLIENT": ["CLIENT"],
        "DATEREV": ["DATREV", "DATEREV", "DATE_REV"],
        "PPE": ["PPE"],
        "RISQUE": ["RISQUE"],
    }
    mapping_norm = {k: [normalize_header(c) for c in v] for k, v in mapping.items()}
    required_keys = ["AGENCE", "EXPL", "CLIENT"]

    for code in filiales:
        nom_filiale_complet = f"BOA {code}"
        fichier = resolve_path(SCORING_PATTERN, code)

        if not os.path.exists(fichier):
            logger.warning(f"missing file: {fichier}")
            continue

        deleted = exec_delete_by_filiale(conn, TABLE_DATEREV, "FILIALE", nom_filiale_complet)
        logger.info(f"cleaned {deleted} rows for {nom_filiale_complet}")

        buffer = []
        inserted_for_filiale = 0
        last_log_limit = LOG_STEP

        encodings = [detect_encoding(fichier), "utf-8-sig", "latin-1", "cp1252"]
        seen = set()
        encodings = [e for e in encodings if not (e in seen or seen.add(e))]

        for enc in encodings:
            try:
                with open(fichier, "r", encoding=enc) as f:
                    reader = csv.DictReader(f, delimiter=DELIMITEUR)
                    if reader.fieldnames:
                        reader.fieldnames = [normalize_header(fn) for fn in reader.fieldnames]
                        logger.debug(f"[{code}] daterev encoding={enc} headers={reader.fieldnames}")
                    else:
                        logger.error(f"empty headers for {code}")
                        break

                    header_set = set(reader.fieldnames)
                    missing = []
                    for key in required_keys:
                        if not any(c in header_set for c in mapping_norm[key]):
                            missing.append(key)
                    if missing:
                        logger.error(f"missing required columns for {code}: {missing}")
                        break

                    for line_num, row in enumerate(reader, start=1):
                        try:
                            row_norm = {normalize_header(k): (v or "") for k, v in row.items()}
                            dt_raw = pick_value(row_norm, mapping_norm["DATEREV"])
                            parsed_dt = parse_date_multi(dt_raw) if dt_raw else None

                            def trunc(val, n):
                                return (val or "").strip()[:n]

                            agence = pick_value(row_norm, mapping_norm["AGENCE"])
                            if not agence:
                                continue

                            values = (
                                nom_filiale_complet,
                                trunc(agence, 10),
                                trunc(pick_value(row_norm, mapping_norm["LIB_AGENCE"]), 50),
                                trunc(pick_value(row_norm, mapping_norm["EXPL"]), 10),
                                trunc(pick_value(row_norm, mapping_norm["CLIENT"]), 10),
                                parsed_dt,
                                trunc(pick_value(row_norm, mapping_norm["PPE"]), 20),
                                trunc(pick_value(row_norm, mapping_norm["RISQUE"]), 20),
                            )
                            buffer.append(values)

                            if len(buffer) >= BULK_SIZE_DATEREV:
                                inserted_for_filiale += bulk_insert(
                                    conn,
                                    TABLE_DATEREV,
                                    [
                                        "FILIALE",
                                        "AGENCE",
                                        "LIB_AGENCE",
                                        "EXPL",
                                        "CLIENT",
                                        "DATEREV",
                                        "PPE",
                                        "RISQUE",
                                    ],
                                    buffer,
                                    BULK_SIZE_DATEREV,
                                )
                                buffer.clear()

                                if inserted_for_filiale >= last_log_limit:
                                    logger.info(f"progress {code}: {inserted_for_filiale} rows")
                                    last_log_limit += LOG_STEP

                        except Exception as e:
                            if line_num % 10000 == 0:
                                logger.error(f"line {line_num} error: {e}")
                            continue

                    if buffer:
                        inserted_for_filiale += bulk_insert(
                            conn,
                            TABLE_DATEREV,
                            [
                                "FILIALE",
                                "AGENCE",
                                "LIB_AGENCE",
                                "EXPL",
                                "CLIENT",
                                "DATEREV",
                                "PPE",
                                "RISQUE",
                            ],
                            buffer,
                            BULK_SIZE_DATEREV,
                        )

                total += inserted_for_filiale
                logger.info(f"done {code}: {inserted_for_filiale} rows")
                break

            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.error(f"critical error on {code}: {e}")
                break

    logger.info(f"DATEREV total: {total} rows")

# =====================================================
# 7. IMPORT TAUX FILIALES
# =====================================================
def import_taux_filiales(conn, filiales):
    logger.info("START TAUX_FILIALES")
    for code in filiales:
        nom_filiale_complet = f"BOA {code}"
        fichier = resolve_path(SUIVI_PATTERN, code)

        if not os.path.exists(fichier):
            logger.warning(f"missing taux file: {fichier}")
            continue

        deleted = exec_delete_by_filiale(conn, TABLE_TAUX_FILIALE, "filiale", nom_filiale_complet)
        logger.info(f"cleaned {deleted} rows for {nom_filiale_complet}")

        buffer, dates_vues, inserted = [], set(), 0

        encodings = [detect_encoding(fichier), "utf-8-sig", "latin-1", "cp1252"]
        seen = set()
        encodings = [e for e in encodings if not (e in seen or seen.add(e))]

        try:
            with open(fichier, "r", encoding=encodings[0], errors="replace") as f:
                reader = csv.DictReader(f, delimiter=DELIMITEUR)
                orig_fields = reader.fieldnames if reader.fieldnames else []
                norm_fields = [normalize_header(fld) for fld in orig_fields]
                reader.fieldnames = norm_fields
                logger.debug(f"[{code}] taux_filiales encoding={encodings[0]} headers={norm_fields}")

                date_key = next((k for k in norm_fields if "DATE" in k), None)
                flux_pm_key = next((k for k in norm_fields if "FLUX" in k and "PM" in k), None)
                flux_pp_key = next((k for k in norm_fields if "FLUX" in k and "PP" in k), None)
                stock_pm_key = next((k for k in norm_fields if "STOCK" in k and "PM" in k), None)
                stock_pp_key = next((k for k in norm_fields if "STOCK" in k and "PP" in k), None)

                if not date_key:
                    logger.error(f"no DATE column detected for {code}")
                    continue
                if not any([flux_pm_key, flux_pp_key, stock_pm_key, stock_pp_key]):
                    logger.error(f"no FLUX/STOCK columns detected for {code}")
                    continue

                for row in reader:
                    try:
                        date_str = row.get(date_key)
                        date_obj = parse_date_multi(date_str)
                        if not date_obj or date_obj in dates_vues:
                            continue

                        val_flux_pm = row.get(flux_pm_key, 0) if flux_pm_key else 0
                        val_flux_pp = row.get(flux_pp_key, 0) if flux_pp_key else 0
                        val_stock_pm = row.get(stock_pm_key, 0) if stock_pm_key else 0
                        val_stock_pp = row.get(stock_pp_key, 0) if stock_pp_key else 0

                        values = (
                            nom_filiale_complet,
                            parse_taux(val_flux_pm),
                            parse_taux(val_flux_pp),
                            parse_taux(val_stock_pm),
                            parse_taux(val_stock_pp),
                            date_obj,
                            datetime.now(),
                        )
                        buffer.append(values)
                        dates_vues.add(date_obj)

                        if len(buffer) >= BULK_SIZE_TAUX_FILIALE:
                            inserted += bulk_insert(
                                conn,
                                TABLE_TAUX_FILIALE,
                                [
                                    "filiale",
                                    "flux_PM",
                                    "flux_PP",
                                    "stock_PM",
                                    "stock_PP",
                                    "date",
                                    "created_at",
                                ],
                                buffer,
                                BULK_SIZE_TAUX_FILIALE,
                            )
                            buffer.clear()
                    except Exception as e:
                        logger.error(f"row error: {e}")
                        continue

                if buffer:
                    inserted += bulk_insert(
                        conn,
                        TABLE_TAUX_FILIALE,
                        [
                            "filiale",
                            "flux_PM",
                            "flux_PP",
                            "stock_PM",
                            "stock_PP",
                            "date",
                            "created_at",
                        ],
                        buffer,
                        BULK_SIZE_TAUX_FILIALE,
                    )

            logger.info(f"{code}: {inserted} rows imported")
        except Exception as e:
            logger.error(f"{code} critical error: {e}")

    logger.info("END TAUX_FILIALES")

# =====================================================
# 8. MAIN
# =====================================================
if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="KYC import MSSQL")

        parser.add_argument("--filiales", help="Liste des filiales: SN,CI,BF")
        parser.add_argument("--data-dir", dest="data_dir", help="Base directory for CSV files")
        parser.add_argument("--anomalies-pattern", dest="anomalies_pattern")
        parser.add_argument("--scoring-pattern", dest="scoring_pattern")
        parser.add_argument("--suivi-pattern", dest="suivi_pattern")

        args = parser.parse_args()

        if args.data_dir:
            globals()["CHEMIN_BASE"] = args.data_dir
            globals()["ANOMALIES_PATTERN"] = os.path.join(CHEMIN_BASE, "anomalies_{code}.csv")
            globals()["SCORING_PATTERN"] = os.path.join(CHEMIN_BASE, "scoring_{code}.csv")
            globals()["SUIVI_PATTERN"] = os.path.join(CHEMIN_BASE, "suivi_fiabilisation_{code}.csv")

        if args.anomalies_pattern:
            globals()["ANOMALIES_PATTERN"] = args.anomalies_pattern
        if args.scoring_pattern:
            globals()["SCORING_PATTERN"] = args.scoring_pattern
        if args.suivi_pattern:
            globals()["SUIVI_PATTERN"] = args.suivi_pattern

        filiales = build_filiales_codes(args.filiales)
        logger.info(f"Filiales utilisées: {filiales}")
        logger.info(f"CHEMIN_BASE: {CHEMIN_BASE}")

        only_raw = os.environ.get("KYC_ONLY", "").strip()
        only = []
        if only_raw:
            only = [p.strip().lower() for p in only_raw.replace(";", ",").split(",") if p.strip()]

        conn = get_conn()
        try:
            if not only or "anomalies" in only:
                import_anomalies(conn, filiales)

            if not only or "daterev" in only:
                import_daterev(conn, filiales)

            if not only or "taux_filiales" in only:
                import_taux_filiales(conn, filiales)
        finally:
            conn.close()

        logger.info("IMPORT DONE")

    except Exception as e:
        logger.critical(f"STOP - FATAL ERROR: {e}")
