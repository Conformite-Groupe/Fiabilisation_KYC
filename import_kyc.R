#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  if (!requireNamespace("DBI", quietly = TRUE)) {
    stop("Package 'DBI' is required. Install with install.packages('DBI').")
  }
})

get_script_dir <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg)) {
    return(dirname(normalizePath(sub("^--file=", "", file_arg[1]))))
  }
  return(getwd())
}

BASE_DIR <- get_script_dir()
DATA_DIR <- Sys.getenv("KYC_DATA_DIR", file.path(BASE_DIR, "data"))
BULK_SIZE <- suppressWarnings(as.integer(Sys.getenv("KYC_BULK_SIZE", "10000")))
if (is.na(BULK_SIZE) || BULK_SIZE <= 0) BULK_SIZE <- 10000

filiales_choices <- c(
  "BOA NE","BOA CI","BOA TG","BOA SN","BOA ML","BOA BF","BOA BJ","BOA RDC",
  "LCB","BCB","BOA MR","BOA MG","BOA UG","BOA TZ","BOA RW","BOA KE","BOA FR",
  "BOA KM","BOA GH","BOA Group"
)

get_filiales_codes <- function() {
  override <- Sys.getenv("KYC_FILIALES", "")
  if (nzchar(override)) {
    parts <- unlist(strsplit(gsub(";", ",", override), ","))
    parts <- trimws(parts)
    return(parts[nzchar(parts)])
  }
  boa <- filiales_choices[grepl("^BOA ", filiales_choices)]
  return(trimws(sub("^BOA ", "", boa)))
}

normalize_headers <- function(x) toupper(trimws(x))

pick_col <- function(dt, candidates) {
  candidates <- intersect(candidates, names(dt))
  if (length(candidates) == 0) {
    return(rep("", nrow(dt)))
  }
  out <- dt[[candidates[1]]]
  out <- ifelse(is.na(out), "", as.character(out))
  if (length(candidates) > 1) {
    for (c in candidates[-1]) {
      add <- dt[[c]]
      add <- ifelse(is.na(add), "", as.character(add))
      mask <- out == ""
      out[mask] <- add[mask]
    }
  }
  return(out)
}

clean_numeric_str <- function(x) {
  x <- ifelse(is.na(x), "", as.character(x))
  x <- gsub(",", ".", x, fixed = TRUE)
  x <- gsub(" ", "", x, fixed = TRUE)
  x
}

read_csv_fallback <- function(path, delim = ";") {
  encs <- c("UTF-8", "UTF-8-BOM", "latin1", "Windows-1252")
  for (enc in encs) {
    dt <- tryCatch({
      if (requireNamespace("data.table", quietly = TRUE)) {
        data.table::fread(path, sep = delim, encoding = enc, na.strings = c("", "NA", "NULL", "NaN"))
      } else {
        read.csv(path, sep = delim, stringsAsFactors = FALSE, fileEncoding = enc)
      }
    }, error = function(e) NULL)
    if (!is.null(dt)) {
      names(dt) <- normalize_headers(names(dt))
      return(dt)
    }
  }
  stop(paste("Failed to read file:", path))
}

connect_db <- function() {
  engine <- tolower(Sys.getenv("DB_ENGINE", "sqlite"))
  if (engine %in% c("sqlite", "sqlite3")) {
    if (!requireNamespace("RSQLite", quietly = TRUE)) {
      stop("Package 'RSQLite' is required for sqlite. Install with install.packages('RSQLite').")
    }
    db_path <- Sys.getenv("DB_PATH", file.path(BASE_DIR, "db.sqlite3"))
    return(DBI::dbConnect(RSQLite::SQLite(), dbname = db_path))
  }
  if (engine %in% c("mssql", "sqlserver")) {
    if (!requireNamespace("odbc", quietly = TRUE)) {
      stop("Package 'odbc' is required for SQL Server. Install with install.packages('odbc').")
    }
    drv <- Sys.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    host <- Sys.getenv("DB_HOST", "")
    name <- Sys.getenv("DB_NAME", "")
    user <- Sys.getenv("DB_USER", "")
    pass <- Sys.getenv("DB_PASSWORD", "")
    port <- Sys.getenv("DB_PORT", "1433")
    trust <- Sys.getenv("DB_TRUST_CERT", "yes")
    return(DBI::dbConnect(odbc::odbc(),
                          Driver = drv, Server = host, Database = name,
                          UID = user, PWD = pass, Port = port,
                          TrustServerCertificate = trust))
  }
  stop("Unsupported DB_ENGINE. Use sqlite or mssql.")
}

append_chunks <- function(con, table, df, chunk_size) {
  if (nrow(df) == 0) return(invisible(0))
  total <- 0
  for (i in seq(1, nrow(df), by = chunk_size)) {
    chunk <- df[i:min(i + chunk_size - 1, nrow(df)), , drop = FALSE]
    DBI::dbAppendTable(con, table, chunk)
    total <- total + nrow(chunk)
  }
  invisible(total)
}

con <- connect_db()
on.exit(DBI::dbDisconnect(con), add = TRUE)

filiales <- get_filiales_codes()
table_pm <- "kyc_kyc_pm"
table_pp <- "kyc_kyc_pp"

map_pm <- list(
  AGENCE = c("AGENCE"),
  LIB_AGENCE = c("LIB_AGENCE", "AGENCELIB"),
  EXPL = c("EXPL"),
  CLIENT = c("CLIENT"),
  AGEC = c("AGEC"),
  CODAPE = c("CODAPE"),
  IDM = c("IDM"),
  RCSNO = c("RCSNO"),
  CAPITAL = c("CAPITAL"),
  CA = c("CA"),
  RESULTAT = c("RESULTAT"),
  ORIGINE_REV = c("ORIGINE_REV", "ORIGINE_REVENU"),
  DATOUV = c("DATOUV"),
  TEL = c("TEL"),
  DEVISE = c("DEVISE"),
  RESID = c("RESID")
)

map_pp <- list(
  AGENCE = c("AGENCE"),
  LIB_AGENCE = c("LIB_AGENCE", "AGENCELIB"),
  EXPL = c("EXPL"),
  CLIENT = c("CLIENT"),
  CODAPE = c("CODAPE"),
  IDP = c("IDP"),
  PAYNAIS = c("PAYNAIS"),
  PROFESSION = c("PROFESSION"),
  ADRESSE = c("ADRESSE"),
  PAYS_RESID = c("PAYS_RESID"),
  NUMID = c("NUMID"),
  SALAIRE = c("SALAIRE"),
  ORIGINE_REV = c("ORIGINE_REV", "ORIGINE_REVENU"),
  DATVALID = c("DATVALID"),
  TEL = c("TEL"),
  DATOUV = c("DATOUV"),
  PPE = c("PPE"),
  DEVISE = c("DEVISE"),
  RESID = c("RESID")
)

for (code in filiales) {
  filiale_val <- paste("BOA", code)
  message(">>> FILIALE ", code)

  DBI::dbExecute(con, paste0("DELETE FROM ", table_pm, " WHERE FILIALE = ?"), params = list(filiale_val))
  DBI::dbExecute(con, paste0("DELETE FROM ", table_pp, " WHERE FILIALE = ?"), params = list(filiale_val))

  pm_path <- file.path(DATA_DIR, paste0("pm_", code, "_STOCK_F.csv"))
  if (file.exists(pm_path)) {
    dt <- read_csv_fallback(pm_path)
    out <- data.frame(FILIALE = rep(filiale_val, nrow(dt)), stringsAsFactors = FALSE)
    for (k in names(map_pm)) {
      out[[k]] <- pick_col(dt, normalize_headers(map_pm[[k]]))
    }
    out$CAPITAL <- clean_numeric_str(out$CAPITAL)
    out$CA <- clean_numeric_str(out$CA)
    out$RESULTAT <- clean_numeric_str(out$RESULTAT)
    append_chunks(con, table_pm, out, BULK_SIZE)
  }

  pp_path <- file.path(DATA_DIR, paste0("pp_", code, "_STOCK_F.csv"))
  if (file.exists(pp_path)) {
    dt <- read_csv_fallback(pp_path)
    out <- data.frame(FILIALE = rep(filiale_val, nrow(dt)), stringsAsFactors = FALSE)
    for (k in names(map_pp)) {
      out[[k]] <- pick_col(dt, normalize_headers(map_pp[[k]]))
    }
    append_chunks(con, table_pp, out, BULK_SIZE)
  }
}

message("Import KYC terminé.")
