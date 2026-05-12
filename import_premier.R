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

parse_date_vec <- function(x) {
  x <- ifelse(is.na(x), "", as.character(x))
  x <- trimws(x)
  x[x == ""] <- NA
  x <- gsub("[^0-9/-]", "", x)
  out <- as.Date(x, format = "%Y-%m-%d")
  idx <- is.na(out) & !is.na(x)
  out[idx] <- as.Date(x[idx], format = "%d/%m/%Y")
  idx <- is.na(out) & !is.na(x)
  out[idx] <- as.Date(x[idx], format = "%d/%m/%y")
  idx <- is.na(out) & !is.na(x)
  out[idx] <- as.Date(x[idx], format = "%Y/%m/%d")
  out
}

parse_taux <- function(x) {
  x <- ifelse(is.na(x), "", as.character(x))
  x <- gsub("%", "", x, fixed = TRUE)
  x <- gsub(",", ".", x, fixed = TRUE)
  suppressWarnings(as.numeric(trimws(x)))
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

table_anom <- "kyc_anomalie"
table_daterev <- "kyc_daterev"
table_taux_filiale <- "kyc_tauxevolution_filiale"
table_taux <- "kyc_tauxevolution"

import_anomalies <- function() {
  for (code in filiales) {
    filiale_val <- paste("BOA", code)
    path <- file.path(DATA_DIR, paste0("anomalies_", code, ".csv"))
    if (!file.exists(path)) next
    DBI::dbExecute(con, paste0("DELETE FROM ", table_anom, " WHERE FILIALE = ?"), params = list(filiale_val))
    dt <- read_csv_fallback(path)
    out <- data.frame(
      FILIALE = rep(filiale_val, nrow(dt)),
      AGENCE = pick_col(dt, c("AGENCE","AG","CODE_AGENCE")),
      LIB_AGENCE = pick_col(dt, c("AGENCELIB","LIB_AGENCE")),
      EXPL = pick_col(dt, c("EXPL")),
      CLIENT = pick_col(dt, c("CLIENT")),
      ANOMALIE_AGE = clean_numeric_str(pick_col(dt, c("ANOMALIE_AGE"))),
      ANOMALIE_DATE_EER = clean_numeric_str(pick_col(dt, c("ANOMALIE_DATE_EER"))),
      ANOMALIE_CIN = clean_numeric_str(pick_col(dt, c("ANOMALIE_CIN"))),
      PPE = clean_numeric_str(pick_col(dt, c("PPE"))),
      stringsAsFactors = FALSE
    )
    append_chunks(con, table_anom, out, 5000)
  }
}

import_daterev <- function() {
  for (code in filiales) {
    filiale_val <- paste("BOA", code)
    path <- file.path(DATA_DIR, paste0("scoring_", code, ".csv"))
    if (!file.exists(path)) next
    DBI::dbExecute(con, paste0("DELETE FROM ", table_daterev, " WHERE FILIALE = ?"), params = list(filiale_val))
    dt <- read_csv_fallback(path)
    out <- data.frame(
      FILIALE = rep(filiale_val, nrow(dt)),
      AGENCE = substr(pick_col(dt, c("AGENCE","AG")), 1, 10),
      LIB_AGENCE = substr(pick_col(dt, c("AGENCELIB","LIB_AGENCE")), 1, 50),
      EXPL = substr(pick_col(dt, c("EXPL")), 1, 10),
      CLIENT = substr(pick_col(dt, c("CLIENT")), 1, 10),
      DATEREV = parse_date_vec(pick_col(dt, c("DATREV","DATEREV","DATE_REV"))),
      PPE = substr(pick_col(dt, c("PPE")), 1, 20),
      RISQUE = substr(pick_col(dt, c("RISQUE")), 1, 20),
      stringsAsFactors = FALSE
    )
    append_chunks(con, table_daterev, out, 20000)
  }
}

import_taux_filiales <- function() {
  for (code in filiales) {
    filiale_val <- paste("BOA", code)
    path <- file.path(DATA_DIR, paste0("suivi_fiabilisation_", code, ".csv"))
    if (!file.exists(path)) next
    DBI::dbExecute(con, paste0("DELETE FROM ", table_taux_filiale, " WHERE filiale = ?"), params = list(filiale_val))
    dt <- read_csv_fallback(path)
    date_col <- names(dt)[grep("DATE", names(dt))[1]]
    flux_pm_col <- names(dt)[grep("FLUX.*PM", names(dt))[1]]
    flux_pp_col <- names(dt)[grep("FLUX.*PP", names(dt))[1]]
    stock_pm_col <- names(dt)[grep("STOCK.*PM", names(dt))[1]]
    stock_pp_col <- names(dt)[grep("STOCK.*PP", names(dt))[1]]
    if (is.na(date_col)) next
    out <- data.frame(
      filiale = rep(filiale_val, nrow(dt)),
      flux_PM = parse_taux(if (!is.na(flux_pm_col)) dt[[flux_pm_col]] else NA),
      flux_PP = parse_taux(if (!is.na(flux_pp_col)) dt[[flux_pp_col]] else NA),
      stock_PM = parse_taux(if (!is.na(stock_pm_col)) dt[[stock_pm_col]] else NA),
      stock_PP = parse_taux(if (!is.na(stock_pp_col)) dt[[stock_pp_col]] else NA),
      date = parse_date_vec(dt[[date_col]]),
      created_at = Sys.time(),
      stringsAsFactors = FALSE
    )
    out <- out[!is.na(out$date), , drop = FALSE]
    append_chunks(con, table_taux_filiale, out, 500)
  }
}

import_taux <- function() {
  clear_flag <- Sys.getenv("KYC_TAUX_CLEAR", "")
  for (code in filiales) {
    filiale_val <- paste("BOA", code)
    path <- file.path(DATA_DIR, paste0("taux_", code, ".csv"))
    if (!file.exists(path)) next
    if (tolower(clear_flag) %in% c("1","true","yes")) {
      DBI::dbExecute(con, paste0("DELETE FROM ", table_taux, " WHERE filiale = ?"), params = list(filiale_val))
    }
    dt <- read_csv_fallback(path)
    agent <- pick_col(dt, c("AGENTS","EXPL"))
    date <- parse_date_vec(pick_col(dt, c("DATE")))
    taux <- parse_taux(pick_col(dt, c("TAUX")))
    flux_stock <- pick_col(dt, c("FLUX_STOCK"))
    pp_pm <- pick_col(dt, c("PP_PM"))
    out <- data.frame(
      filiale = rep(filiale_val, nrow(dt)),
      agence = NA,
      expl = agent,
      date = date,
      taux = taux,
      created_at = Sys.time(),
      flux_stock = flux_stock,
      pp_pm = pp_pm,
      stringsAsFactors = FALSE
    )
    out <- out[!is.na(out$date) & out$expl != "", , drop = FALSE]
    if (nrow(out) > 0) {
      if (requireNamespace("data.table", quietly = TRUE)) {
        out <- data.table::unique(data.table::as.data.table(out),
                                  by = c("filiale","expl","date","pp_pm","flux_stock"))
        out <- as.data.frame(out)
      } else {
        out <- unique(out)
      }
    }
    append_chunks(con, table_taux, out, 5000)
  }
}

only <- Sys.getenv("KYC_ONLY", "")
only <- tolower(trimws(only))

if (only == "" || grepl("anomal", only)) import_anomalies()
if (only == "" || grepl("daterev", only)) import_daterev()
if (only == "" || grepl("taux_fil", only)) import_taux_filiales()
if (only == "" || grepl("taux", only)) import_taux()

message("Import premier terminé.")
