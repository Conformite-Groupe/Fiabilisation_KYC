#####-----------------------IMPORTATION DES LIBRAIRIES-------------###########
      
cat("###############################################\n")
cat("######### P3 - FIABILISATION DES DONNEES KYC \n")
cat("######### ETAPE 1/3: CHAMPS A FIABILISER\n")
cat("##############################################\n")

options(warn = -1)

suppressPackageStartupMessages({
library(kableExtra)
library(officer)
library(flextable)
library(openxlsx)
library(scales)
library(purrr)
library(xts)
library(lubridate)
library(dplyr)
library(tidyr)
library(ggplot2)
library(rvg)
library(patchwork)
library(zip)
library(ggrepel)
library(readxl)
library(readr)
library(stringi)
library(data.table)

})

#####-----------------------CONFIG ET FONCTIONS-------------###########
chemin <- "C://Users//mamsylla//OneDrive - BANK OF AFRICA (1)//data//"
chemin2="C://KYC_Filiales//"
chemin_7z <- '"C://Program Files//7-Zip//7z.exe"'
#####-----------------------####-------------###########

#####--------------DATES ( à modifier en prod) ------###########
#
  #premier_jour_mois_courant <- floor_date(premier_jour_mois_precedent, "month")
  #premier_jour_mois_precedent <- premier_jour_mois_courant %m-% months(1)

 premier_jour_mois_courant <- "2026-06-01"
 premier_jour_mois_precedent <- "2026-05-01"

 # premier_jour_mois_courant <- premier_jour_mois_precedent

 # premier_jour_mois_precedent <- premier_jour_mois_precedent-1


  date_limite <- as.Date("2024/10/01") %m-% months(3)



#####-----------------------####-------------###########

prerequis=read.csv2(paste(sep="",chemin,"prerequis.csv"),header=F)

colnames(prerequis)=c("infos","argument","LIB_ETUDIANT","LIB_MINEUR")


filiale=prerequis$infos[prerequis$argument=="y"]


trimestre_actuel=as.character(prerequis[1,2])


inc=c("")


  pp_fields <- c("PAYNAIS","PROFESSION","SALAIRE","NUMID","CODAPE","TEL","DATNAIS","ADRESSE","DATVALID","ORIGINE_REVENU")
  pm_fields <- c("CODAPE","AGEC","CAPITAL","CA","RESULTAT","RCSNO","ORIGINE_REVENU","TEL")
 
for (r in filiale) {
    repertoire=file.path(chemin,r)
    dir.create(repertoire)

}

## Fonctions 

pair <- function(nombre) {
  if (nombre %% 2 == 0) {
    return(TRUE)
  } else {
    return(FALSE)
  }
}

compress <- function(x, sep = " ", dec = ",", digits = 0) {
  formatC(x, format = "f", big.mark = sep, decimal.mark = dec, digits = digits)
}




is_alphanumeric <- function(x) {
  if (is.character(x)) {
    x2 <- suppressWarnings(iconv(x, from = "", to = "UTF-8", sub = ""))
    bad <- is.na(x2)
    if (any(bad)) {
      x2[bad] <- suppressWarnings(iconv(x[bad], from = "latin1", to = "UTF-8", sub = ""))
    }
    x <- x2
  }
  grepl("[a-zA-Z]", x, useBytes = TRUE) | grepl("[0-9]", x, useBytes = TRUE)
}


remove_spaces <- function(x) {
  if (is.character(x)) {
    # Normalise encodage (gère les octets invalides)
    x2 <- suppressWarnings(iconv(x, from = "", to = "UTF-8", sub = ""))
    bad <- is.na(x2)
    if (any(bad)) {
      x2[bad] <- suppressWarnings(iconv(x[bad], from = "latin1", to = "UTF-8", sub = ""))
    }
    return(trimws(gsub("\\t", "", x2, useBytes = TRUE)))
  }
  return(x)
}

# Classe de caracteres "espace" a normaliser : tabulation, espace ordinaire,
# insecable (U+00A0), insecable etroit (U+202F), espace chiffre (U+2007).
# Caracteres litteraux et non echappements \x{...} : PCRE refuse ces derniers
# quand la chaine traitee n'est pas marquee UTF-8 (cas des exports Latin-1).
ESPACES_PARASITES <- paste0("[\t ", intToUtf8(160), intToUtf8(8239), intToUtf8(8199), "]+")

# Colonnes a NE PAS charger, par filiale. Elles sont ecartees des la lecture
# (drop de fread) : elles n'occupent donc jamais de memoire. Une colonne listee
# ici mais absente de l'export est simplement signalee, sans erreur.
COLONNES_IGNOREES <- list(
  MG = c("INTITULE_COMPTE", "LIEU_DELIVRANCE_CIN", "BOITE_POSTALE", "CONSENT_BIC")
)

# Au-dela de ce seuil, read_csv2_big lit le CSV en NB_TRANCHES morceaux
# (mono-thread) au lieu d'une seule passe. Augmenter NB_TRANCHES si la session
# R meurt encore avec une violation d'acces 0xC0000005.
SEUIL_DECOUPAGE_GO <- 1
NB_TRANCHES <- 4

# Nettoyage des espaces (début/fin + multiples)
clean_spaces <- function(x) {
  x <- ifelse(is.na(x), "", as.character(x))
  if (is.character(x)) {
    orig <- x
    x2 <- suppressWarnings(iconv(orig, from = "", to = "UTF-8", sub = ""))
    bad <- is.na(x2)
    if (any(bad)) {
      x2[bad] <- suppressWarnings(iconv(orig[bad], from = "latin1", to = "UTF-8", sub = ""))
    }
    x <- x2
  }
  x <- gsub(ESPACES_PARASITES, " ", x, perl = TRUE)
  trimws(x)
}

# Force AGENCE to 5 chars with leading zeros
pad_agence5 <- function(x) {
  x <- as.character(x)
  x[is.na(x)] <- ""
  x <- trimws(x)
  idx <- x != "" & nchar(x) < 5
  if (any(idx)) {
    x[idx] <- gsub(" ", "0", sprintf("%5s", x[idx]))
  }
  x
}

# Nettoyage + marquage des valeurs "rep" par colonne (vectorise)
clean_and_mark_anomalies <- function(df, start_col = 4) {
  if (is.null(df) || ncol(df) < start_col) return(df)
  # Trim leading/trailing spaces on all character columns
  df[] <- lapply(df, function(x) if (is.character(x)) trimws(x) else x)
  cols <- start_col:ncol(df)
  df[cols] <- Map(function(x, nm) {
    x[is.na(x)] <- ""
    rep_idx <- is_rep(x)
    if (any(rep_idx, na.rm = TRUE)) {
      x[rep_idx] <- paste("ANOMALIE", nm)
    }
    x
  }, df[cols], names(df)[cols])
  df
}

# Compte le nombre de champs vides sur une liste de colonnes
count_empty_fields <- function(df, fields) {
  if (is.null(df) || length(fields) == 0) return(0L)
  idx <- match(fields, colnames(df))
  idx <- idx[!is.na(idx)]
  if (length(idx) == 0) return(0L)
  sum(sapply(df[, idx, drop = FALSE], function(x) {
    x <- trimws(as.character(x))
    sum(is.na(x) | x == "")
  }))
}

field_completion_rate <- function(df, field, inc = c("")) {
  if (is.null(df) || nrow(df) == 0 || !(field %in% names(df))) return(NA_real_)
  x <- trimws(as.character(df[[field]]))
  floor(100 - (sum(is.na(x) | x %in% inc) / nrow(df)) * 100)
}

compute_taux <- function(df, fields) {
  if (is.null(df) || nrow(df) == 0 || length(fields) == 0) return(NA_real_)
  cv <- count_empty_fields(df, fields)
  floor(100 * (1 - (cv / (length(fields) * nrow(df)))))
}

format_percent <- function(x) {
  if (length(x) == 0 || is.na(x)) "N/A" else paste0(x, "%")
}

min_rate <- function(...) {
  values <- c(...)
  if (length(values) == 0 || all(is.na(values))) NA_real_ else min(values, na.rm = TRUE)
}

get_appreciation <- function(taux, faible, moyen) {
  if (length(taux) == 0 || is.na(taux)) {
    "Aucune donnée"
  } else if (taux < faible) {
    "Faible"
  } else if (taux >= faible & taux < moyen) {
    "Moyen"
  } else {
    "Bon"
  }
}

get_taux_ratt <- function(taux, trimestre, label_retard = TRUE) {
  if (length(taux) == 0 || is.na(taux)) return("N/A")
  taux_rat <- floor(trimestre - taux)
  if (taux_rat < 0) {
    paste("En avance de + ", abs(taux_rat), "%", sep = "")
  } else if (label_retard) {
    paste("En retard de ", taux_rat, "%", sep = "")
  } else {
    paste(taux_rat, "%", sep = "")
  }
}

bind_results <- function(results, template) {
  if (length(results) == 0) return(template[0, , drop = FALSE])
  do.call("rbind", results)
}

empty_anomalies_pp <- function(pp_ne) {
  template <- pp_ne[0, , drop = FALSE]
  template$AGE <- numeric(0)
  template$ANOMALIE_AGE <- character(0)
  template$AGE_EER <- numeric(0)
  template$ANOMALIE_DATE_EER <- character(0)
  template$AGE_CIN <- numeric(0)
  template$ANOMALIE_CIN <- character(0)
  template
}

reset_row_names <- function(data) {
  if (is.data.frame(data)) row.names(data) <- NULL
  data
}

# Selection des colonnes PP par nom, independamment de leur position dans l'export
select_pp_fields <- function(df, fields) {
  names(df) <- toupper(names(df))
  context_fields <- c("AGENCE", "EXPL", "CLIENT","IDP","DATOUV")
  fields <- toupper(fields)
  selected_fields <- c(context_fields, fields)
  missing_fields <- setdiff(selected_fields, names(df))

  for (field in missing_fields) {
    df[[field]] <- ""
  }

  df <- df[, selected_fields, drop = FALSE]
  names(df)[names(df) == "ORIGINE_REV"] <- "ORIGINE_REVENU"
  df
}

# Selection des colonnes PM par nom, independamment de leur position dans l'export
select_pm_fields <- function(df, fields) {
  names(df) <- toupper(names(df))
  context_fields <- c("AGENCE", "EXPL", "CLIENT","IDM","DATOUV")
  fields <- toupper(fields)
  selected_fields <- c(context_fields, fields)
  missing_fields <- setdiff(selected_fields, names(df))

  for (field in missing_fields) {
    df[[field]] <- ""
  }

  df <- df[, selected_fields, drop = FALSE]
  names(df)[names(df) == "ORIGINE_REV"] <- "ORIGINE_REVENU"
  df
}

# Nettoie le fichier source si "RCS N°" empêche la lecture
sanitize_rcsno_file <- function(path) {
  if (!file.exists(path)) return(path)
  txt <- readLines(path, encoding = "Latin1", warn = FALSE, skipNul = TRUE)
  Encoding(txt) <- "latin1"
  pat1 <- paste0("RCS N", "\xB0")       # degree in Latin1
  pat2 <- paste0("RCS N", "\xC2\xB0")   # UTF-8 degree read as Latin1 (??)
  if (!any(grepl(pat1, txt, fixed = TRUE, useBytes = TRUE) | grepl(pat2, txt, fixed = TRUE, useBytes = TRUE))) return(path)
  tmp <- paste0(path, ".clean")
  txt <- gsub(pat1, "RCS N", txt, fixed = TRUE, useBytes = TRUE)
  txt <- gsub(pat2, "RCS N", txt, fixed = TRUE, useBytes = TRUE)
  writeLines(txt, tmp, useBytes = TRUE)
  tmp
}

# Parsing robuste des dates (YYYY-MM-DD ou DD/MM/YYYY)
parse_date_any <- function(x) {
  x <- trimws(as.character(x))
  x[x == ""] <- NA
  out <- suppressWarnings(ymd(x))
  idx <- is.na(out)
  if (any(idx)) out[idx] <- suppressWarnings(dmy(x[idx]))
  out
}

# Applique un style par lot selon une colonne de statut
apply_status_style <- function(wb, sheet, data, value_col,
                               col_good = value_col, col_mid = value_col, col_low = value_col,
                               good = "Bon", mid = "Moyen", header_rows = 1,
                               style_good = bonStyle, style_mid = moyenStyle, style_low = lowStyle) {
  if (is.null(data) || nrow(data) == 0) return(invisible(NULL))
  v <- data[[value_col]]
  rows_good <- which(v == good) + header_rows
  if (length(rows_good) > 0) {
    addStyle(wb, sheet, style_good, cols = col_good, rows = rows_good, gridExpand = FALSE, stack = TRUE)
  }
  rows_mid <- which(v == mid) + header_rows
  if (length(rows_mid) > 0) {
    addStyle(wb, sheet, style_mid, cols = col_mid, rows = rows_mid, gridExpand = FALSE, stack = TRUE)
  }
  rows_low <- which(!(v %in% c(good, mid)) & !is.na(v)) + header_rows
  if (length(rows_low) > 0) {
    addStyle(wb, sheet, style_low, cols = col_low, rows = rows_low, gridExpand = FALSE, stack = TRUE)
  }
  invisible(NULL)
}

# Calcule le taux de completude min(PP, PM) par agent (vectorise)
compute_app_flux <- function(taux_pp, taux_pm,
                             agent_col = "Agents", taux_col = "Taux.de.fiabilisation") {
  if (is.null(taux_pp)) taux_pp <- data.frame()
  if (is.null(taux_pm)) taux_pm <- data.frame()

  if (nrow(taux_pp) == 0 && nrow(taux_pm) == 0) {
    return(data.frame(Agents = character(0), Taux_Completude = numeric(0)))
  }

  agents <- unique(c(taux_pp[[agent_col]], taux_pm[[agent_col]]))

  pp_vals <- if (nrow(taux_pp) > 0) {
    setNames(as.numeric(gsub("%", "", taux_pp[[taux_col]])), taux_pp[[agent_col]])
  } else {
    setNames(numeric(0), character(0))
  }

  pm_vals <- if (nrow(taux_pm) > 0) {
    setNames(as.numeric(gsub("%", "", taux_pm[[taux_col]])), taux_pm[[agent_col]])
  } else {
    setNames(numeric(0), character(0))
  }

  pp_aligned <- pp_vals[agents]
  pm_aligned <- pm_vals[agents]

  min_vals <- ifelse(is.na(pp_aligned), pm_aligned,
                     ifelse(is.na(pm_aligned), pp_aligned, pmin(pp_aligned, pm_aligned)))

  data.frame(Agents = agents, Taux_Completude = unname(min_vals), stringsAsFactors = FALSE)
}



is_rep <- function(x) {

    (grepl("XX", x) & nchar(x)==2)  | (grepl("RAS", x) & nchar(x)==3)  | (grepl("R.A.S.", x) & nchar(x)==6) | (grepl("R.A.S", x) & nchar(x)==5) | nchar(x)==1
}

# Fonction pour nettoyer les noms de colonnes (BOM et mauvais encodage)
clean_colnames <- function(data) {
    # Supprime les caractères de BOM et mauvais encodage au début
    names(data) <- gsub("^[\\xef\\xbb\\xbf\\u00ef\\u00bb\\u00bf]|^ï\\.\\.\\.?|^ï\\.\\.|^ï\\.\\xef", "", names(data))
    return(data)
}

# Detection automatique d'encodage (heuristique rapide)
detect_encoding <- function(path, n = 100000) {
  con <- file(path, "rb")
  on.exit(close(con), add = TRUE)
  raw <- readBin(con, "raw", n = n)

  if (length(raw) >= 3 &&
      raw[1] == as.raw(0xEF) &&
      raw[2] == as.raw(0xBB) &&
      raw[3] == as.raw(0xBF)) {
    return("UTF-8-BOM")
  }

  raw_nz <- raw[raw != as.raw(0x00)]
  if (length(raw_nz) == 0) {
    return("UTF-8")
  }

  txt <- tryCatch(
    iconv(rawToChar(raw_nz), from = "UTF-8", to = "UTF-8", sub = NA),
    error = function(e) NA
  )
  if (!is.na(txt)) {
    return("UTF-8")
  }

  return("Windows-1252")
}

# Lecture CSV2 avec encodage auto + correction si besoin


# Nettoyage post-lecture : enlève les guillemets, préserve accents/trémas/@
clean_quotes_df <- function(df) {
  char_cols <- vapply(df, is.character, logical(1))
  df[char_cols] <- lapply(df[char_cols], function(x) {
    # Sécurise l'encodage (préserve é, ï, @, etc.)
    x <- enc2utf8(x)
    # Supprime tous les guillemets doubles
    x <- gsub('"', "", x, fixed = TRUE)
    # Nettoie les espaces résiduels en début/fin
    trimws(x)
  })
  # Nettoie aussi les noms de colonnes
  names(df) <- trimws(gsub('"', "", enc2utf8(names(df)), fixed = TRUE))
  df
}

# Lecture CSV2 avec encodage auto + correction si besoin
read_csv2_auto <- function(path, ...) {
  enc_guess <- detect_encoding(path)
  encodings <- unique(c(enc_guess, "UTF-8-BOM", "UTF-8", "Windows-1252", "Latin1"))
  last_error <- NULL
  dots <- list(...)
  if (!"strip.white" %in% names(dots)) dots$strip.white <- TRUE
  # Force la lecture en caractères (évite les conversions en facteurs)
  if (!"stringsAsFactors" %in% names(dots)) dots$stringsAsFactors <- FALSE

  for (enc in encodings) {
    res <- tryCatch(
      withCallingHandlers(
        do.call(read.csv2, c(list(path, fileEncoding = enc), dots)),
        warning = function(w) {
          msg <- conditionMessage(w)
          if (grepl("invalid input|input string|entrée incorrecte|entree incorrecte", msg, ignore.case = TRUE)) {
            invokeRestart("muffleWarning")
            stop("invalid_input_warning")
          }
          if (grepl("incomplete final line", msg, ignore.case = TRUE)) {
            invokeRestart("muffleWarning")
          }
          if (grepl("EOF", msg, ignore.case = TRUE) &&
              grepl("quoted", msg, ignore.case = TRUE)) {
            invokeRestart("muffleWarning")
            stop("eof_quoted_string")
          }
        }
      ),
      error = function(e) e
    )

    if (!inherits(res, "error")) {
      if (!identical(enc, enc_guess)) {
        message("Correction encodage: ", enc)
      }
      return(clean_quotes_df(res))
    }

    last_error <- res

    # Retry sans guillemets si EOF dans chaîne quotée ou entrée invalide
    msg <- conditionMessage(res)
    if (grepl("eof_quoted_string|invalid_input_warning|invalid input|input string|entrée incorrecte|entree incorrecte", msg, ignore.case = TRUE)) {
      dots2 <- dots
      if (!"quote" %in% names(dots2)) dots2$quote <- ""
      if (!"fill" %in% names(dots2)) dots2$fill <- TRUE
      res2 <- tryCatch(
        do.call(read.csv2, c(list(path, fileEncoding = enc), dots2)),
        error = function(e) e
      )
      if (!inherits(res2, "error")) {
        if (!identical(enc, enc_guess)) {
          message("Correction encodage: ", enc)
        }
        message("Correction lecture: guillemets desactives (quote='')")
        return(clean_quotes_df(res2))
      }
    }
  }

  stop("Lecture impossible (encodage). Dernier avertissement: ", conditionMessage(last_error))
}

# Lecture rapide des gros fichiers (pp_stock/pm_stock ~2 Go) via data.table::fread
# - multi-thread, strip.white natif (espaces parasites dans les colonnes)
# - cache .rds : les relances du script rechargent en quelques secondes
# - type.convert reproduit le typage de read.csv2 (dec = ",")
read_csv2_big <- function(path, cache = TRUE, drop = NULL) {
  t0 <- Sys.time()
  # Le cache depend des colonnes ignorees : suffixe distinct pour ne pas
  # recharger un cache complet quand on demande une lecture allegee (ou l'inverse).
  rds <- paste0(path, if (length(drop)) "-drop" else "", ".rds")
  if (cache && file.exists(rds) && file.mtime(rds) >= file.mtime(path)) {
    message("[read_csv2_big] Lecture depuis le cache: ", basename(rds))
    df <- readRDS(rds)
    message("[read_csv2_big] Cache charge en ",
            round(difftime(Sys.time(), t0, units = "secs")), "s (",
            nrow(df), " lignes)")
    return(df)
  }

  message("[read_csv2_big] ", basename(path), " : ",
          round(file.size(path) / 1024^2), " Mo, ",
          data.table::getDTthreads(), " threads fread")

  enc_guess <- detect_encoding(path)
  enc_fread <- if (grepl("UTF-?8", enc_guess, ignore.case = TRUE)) "UTF-8" else "Latin-1"
  message("[read_csv2_big] Encodage fread: ", enc_fread)

  # fill = Inf : certaines lignes ont des champs en trop (";" dans un libellé),
  # sans cela fread s'arrête en cours de fichier (lecture TRONQUEE silencieuse).
  # Le warning "Stopped early" est donc traité comme un échec.
  fread_try <- function(q, skip = 0L, nrows = Inf, col_names = NULL, nthread = NULL,
                        dropcols = NULL) {
    stopped <- FALSE
    args <- list(path, sep = ";", dec = ",", quote = q,
                 colClasses = "character", encoding = enc_fread,
                 strip.white = TRUE, fill = Inf, blank.lines.skip = TRUE,
                 showProgress = TRUE, data.table = TRUE, nrows = nrows)
    if (!is.null(nthread)) args$nThread <- nthread
    # drop par INDICE et non par nom : en mode tranche les colonnes sortent en
    # V1, V2, ... (header = FALSE), un drop par nom ne matcherait rien.
    if (length(dropcols)) args$drop <- dropcols
    if (!is.null(col_names)) {
      # Tranche : on saute l'en-tete + les lignes deja lues (sinon la 1re ligne
      # de donnees servirait d'en-tete et la tranche perdrait une ligne).
      # NE PAS passer col.names ici : cela figerait le nombre de colonnes et
      # les lignes ayant des champs en trop (";" dans un libelle) deborderaient
      # sur une NOUVELLE LIGNE au lieu de creer des colonnes V4, V5...
      # Les colonnes sortent donc en V1, V2, ... et sont renommees apres le
      # recollage, ce qui reproduit exactement la lecture en une passe.
      args$skip <- skip + 1L
      args$header <- FALSE
    }
    df <- withCallingHandlers(
      tryCatch(
        do.call(data.table::fread, args),
        error = function(e) {
          message("[read_csv2_big] fread (quote=", deparse(q), ") a echoue: ",
                  conditionMessage(e))
          NULL
        }
      ),
      warning = function(w) {
        msg <- conditionMessage(w)
        if (grepl("Stopped early|Discarded single-line", msg)) {
          message("[read_csv2_big] Lecture incomplete (quote=", deparse(q), "): ", msg)
          stopped <<- TRUE
        }
        invokeRestart("muffleWarning")
      }
    )
    if (stopped) return(NULL)
    df
  }

  # Répare les octets invalides (fichiers UTF-8 contenant des restes Latin-1),
  # enlève les guillemets et espaces résiduels, puis retype comme read.csv2.
  # validEnc (test C rapide) évite de convertir chaque chaîne : seules les
  # valeurs réellement invalides passent par iconv.
  fix_utf8 <- function(x) {
    bad <- !validEnc(x)
    if (any(bad)) {
      x[bad] <- suppressWarnings(iconv(x[bad], from = "latin1", to = "UTF-8", sub = ""))
    }
    x
  }

  # Nettoyage colonne par colonne PAR REFERENCE (data.table::set).
  # Un "df[] <- lapply(df, ...)" dupliquerait tout le tableau en memoire : sur
  # 3 Go de CSV (soit >10 Go une fois en RAM) cela suffit a faire crasher R
  # avec une violation d'acces 0xC0000005. Ici une seule colonne est en double
  # a un instant donne, et l'ancienne est liberee immediatement.
  # retype = FALSE pour les tranches : le type.convert final se fait une seule
  # fois sur le tableau recolle (sinon deux tranches peuvent recevoir des types
  # differents selon leur contenu, et le rbind echoue ou coerce en silence).
  clean_dt <- function(df, retype = TRUE) {
    for (j in seq_len(ncol(df))) {
      x <- df[[j]]
      x <- fix_utf8(x)
      if (any(grepl('"', x, fixed = TRUE))) {
        x <- gsub('"', "", x, fixed = TRUE)
      }
      # Espaces parasites de l'export : tabulations, espaces insecables et
      # suites d'espaces internes -> un seul espace, puis trim.
      x <- gsub(ESPACES_PARASITES, " ", x, perl = TRUE)
      x <- trimws(x)
      if (retype) x <- type.convert(x, as.is = TRUE, dec = ",")
      data.table::set(df, j = j, value = x)
      rm(x)
      if (j %% 10 == 0) gc(verbose = FALSE)
    }
    gc(verbose = FALSE)
    data.table::setnames(df, trimws(gsub('"', "", fix_utf8(names(df)), fixed = TRUE)))
    df
  }

  taille_go <- file.size(path) / 1024^3

  # ---- Colonnes a ignorer : resolution des noms en INDICES ----
  # Faite sur l'en-tete reel du fichier : une colonne absente de cet export est
  # simplement signalee et ignoree (pas d'erreur), et le drop est ensuite
  # utilisable aussi bien en lecture directe qu'en mode tranche.
  drop_idx <- NULL
  entete_all <- NULL
  if (length(drop)) {
    entete_all <- fread_try("", nrows = 0L)
    if (is.null(entete_all) || ncol(entete_all) < 2) entete_all <- fread_try("\"", nrows = 0L)
    if (!is.null(entete_all)) {
      noms_reels <- trimws(gsub('"', "", names(entete_all), fixed = TRUE))
      drop_idx <- which(toupper(noms_reels) %in% toupper(drop))
      absentes <- setdiff(toupper(drop), toupper(noms_reels))
      if (length(absentes)) {
        message("[read_csv2_big] Colonnes a ignorer absentes du fichier: ",
                paste(absentes, collapse = ", "))
      }
      if (length(drop_idx)) {
        message("[read_csv2_big] Colonnes ignorees (non chargees): ",
                paste(noms_reels[drop_idx], collapse = ", "))
      } else {
        drop_idx <- NULL
      }
    }
  }

  if (taille_go <= SEUIL_DECOUPAGE_GO) {
    # ---- Lecture en une seule passe (fichiers "normaux") ----
    # quote="" en premier : les exports bancaires ont des guillemets mal apparies
    # qui font derailler le parsing quote (fichier lu en 1 seule colonne)
    df <- fread_try("", dropcols = drop_idx)
    if (is.null(df) || ncol(df) < 2) {
      message("[read_csv2_big] Nouvel essai avec quote standard ...")
      df <- fread_try("\"", dropcols = drop_idx)
      if (!is.null(df) && ncol(df) < 2) df <- NULL
    }
    if (is.null(df)) {
      message("[read_csv2_big] ATTENTION: bascule sur read_csv2_auto (LENT, plusieurs minutes)")
      return(read_csv2_auto(path))
    }
    message("[read_csv2_big] fread OK: ", nrow(df), " lignes en ",
            round(difftime(Sys.time(), t0, units = "secs")), "s. Typage...")
    df <- clean_dt(df, retype = TRUE)

  } else {
    # ---- Lecture par tranches (fichiers > SEUIL_DECOUPAGE_GO) ----
    # Chaque tranche est lue puis nettoyee avant de passer a la suivante : le
    # pic memoire du nettoyage porte sur 1/N du fichier au lieu du tout.
    # nThread = 1 : le parsing multi-thread de fread sur fichier malforme
    # (champs en trop, guillemets mal apparies) est une cause connue de crash
    # 0xC0000005 ; la lecture est plus lente mais ne tue pas la session.
    message("[read_csv2_big] Fichier de ", round(taille_go, 2),
            " Go > ", SEUIL_DECOUPAGE_GO, " Go : lecture en ",
            NB_TRANCHES, " tranches, mono-thread.")

    # En-tete APRES drop : col_names doit decrire les colonnes reellement lues,
    # puisque les tranches sortent en V1, V2, ... et sont renommees dessus.
    entete <- fread_try("", nrows = 0L, dropcols = drop_idx)
    if (is.null(entete) || ncol(entete) < 2) {
      entete <- fread_try("\"", nrows = 0L, dropcols = drop_idx)
    }
    if (is.null(entete) || ncol(entete) < 2) {
      message("[read_csv2_big] ATTENTION: en-tete illisible, bascule sur read_csv2_auto")
      return(read_csv2_auto(path))
    }
    col_names <- names(entete)
    quote_ok <- ""

    # Taille de tranche ESTIMEE a partir de la longueur moyenne des 1000
    # premieres lignes. Volontairement pas de comptage exact prealable : un
    # fread de comptage sur fichier malforme s'arrete tot et sous-compte, ce
    # qui tronquerait les donnees en silence. La boucle ci-dessous lit donc
    # jusqu'a epuisement reel du fichier ; l'estimation ne joue que sur le
    # nombre de tranches, jamais sur l'exhaustivite.
    ech <- readLines(path, n = 1000L, warn = FALSE)
    oct_par_ligne <- max(1, mean(nchar(ech, type = "bytes") + 1))
    n_estime <- max(1, ceiling(file.size(path) / oct_par_ligne))
    par_tranche <- max(1L, as.integer(ceiling(n_estime / NB_TRANCHES)))
    message("[read_csv2_big] ~", n_estime, " lignes estimees -> ",
            par_tranche, " par tranche")

    morceaux <- list()
    i <- 0L
    repeat {
      i <- i + 1L
      saut <- (i - 1L) * par_tranche
      message("[read_csv2_big] Tranche ", i, " (a partir de la ligne ",
              saut + 1L, ") ...")
      tr <- fread_try(quote_ok, skip = saut, nrows = par_tranche,
                      col_names = col_names, nthread = 1L, dropcols = drop_idx)
      if (is.null(tr)) {
        message("[read_csv2_big] Tranche ", i, " illisible, bascule sur read_csv2_auto")
        return(read_csv2_auto(path))
      }
      if (nrow(tr) == 0L) break          # fin de fichier atteinte
      morceaux[[length(morceaux) + 1L]] <- clean_dt(tr, retype = FALSE)
      lu <- nrow(tr)
      rm(tr); gc(verbose = FALSE)
      if (lu < par_tranche) break        # derniere tranche (incomplete)
    }

    message("[read_csv2_big] Recollage des ", length(morceaux), " tranches ...")
    # use.names = TRUE sur des noms positionnels (V1, V2, ...) : les tranches
    # n'ayant pas de ligne malformee ont moins de colonnes, fill = TRUE complete
    # alors par NA, comme le ferait la lecture en une passe.
    df <- data.table::rbindlist(morceaux, use.names = TRUE, fill = TRUE)
    rm(morceaux); gc(verbose = FALSE)

    # Restitution des vrais noms de colonnes ; les colonnes surnumeraires
    # (champs en trop) gardent leur nom positionnel V4, V5, ... comme en une passe.
    n_nommees <- min(length(col_names), ncol(df))
    if (n_nommees > 0L) {
      data.table::setnames(df, seq_len(n_nommees), col_names[seq_len(n_nommees)])
    }

    # Les NA presents ici ne peuvent venir que du fill de rbindlist (colonnes
    # surnumeraires absentes de certaines tranches) : le typage n'a pas encore
    # eu lieu, donc un champ vide du CSV vaut "" et non NA. On restitue "",
    # ce que produit la lecture en une passe.
    for (j in seq_len(ncol(df))) {
      x <- df[[j]]
      if (is.character(x) && anyNA(x)) {
        x[is.na(x)] <- ""
        data.table::set(df, j = j, value = x)
      }
    }

    # Typage final, une seule fois, sur le tableau complet
    for (j in seq_len(ncol(df))) {
      data.table::set(df, j = j,
                      value = type.convert(df[[j]], as.is = TRUE, dec = ","))
      if (j %% 10 == 0) gc(verbose = FALSE)
    }
    gc(verbose = FALSE)
    message("[read_csv2_big] Recollage OK: ", nrow(df), " lignes")
  }

  data.table::setDF(df)   # par reference : pas de copie

  if (cache) {
    message("[read_csv2_big] Ecriture du cache ", basename(rds), " ...")
    # compress = FALSE : gzip mono-thread prendrait plusieurs minutes sur 2 Go
    tryCatch(saveRDS(df, rds, compress = FALSE), error = function(e)
      message("[read_csv2_big] Cache non ecrit (", conditionMessage(e), ")"))
  }
  message("[read_csv2_big] Termine en ",
          round(difftime(Sys.time(), t0, units = "secs")), "s")
  df
}


# Agrege les lignes partageant le meme CLIENT en une seule ligne.
# Pour chaque colonne : valeurs distinctes non vides, separees par une virgule.
#   CLIENT 42 | TEL "0102"  | VILLE "DAKAR"   ->  CLIENT 42 | TEL "0102,0304"
#   CLIENT 42 | TEL "0304"  | VILLE "DAKAR"       VILLE "DAKAR"
# Les colonnes constantes a l'interieur de chaque groupe gardent leur type
# d'origine (numerique, date...) ; seules celles reellement fusionnees passent
# en texte, sinon un "1,2" issu de deux valeurs 1 et 2 serait relu comme le
# nombre 1,2 (dec = ",") et corromprait la donnee.
agreger_par_client <- function(df, cle = "CLIENT") {
  if (is.null(df) || !(cle %in% names(df)) || nrow(df) == 0) return(df)

  ordre <- names(df)
  data.table::setDT(df)

  n_doublons <- sum(duplicated(df[[cle]]))
  if (n_doublons == 0L) {
    message("[agreger_par_client] Aucun ", cle, " en double : rien a agreger.")
    data.table::setDF(df)
    return(df)
  }
  message("[agreger_par_client] ", n_doublons, " ligne(s) en double sur ", cle,
          " -> agregation ...")

  cols <- setdiff(names(df), cle)

  # 1 seule passe groupee pour savoir quelles colonnes varient dans un groupe
  nu <- df[, lapply(.SD, data.table::uniqueN), by = c(cle), .SDcols = cols]
  varie <- vapply(cols, function(cn) any(nu[[cn]] > 1L), logical(1))
  rm(nu); gc(verbose = FALSE)

  cols_fusion <- cols[varie]
  cols_stables <- cols[!varie]
  message("[agreger_par_client] ", length(cols_fusion),
          " colonne(s) fusionnee(s) en texte",
          if (length(cols_fusion)) paste0(" : ", paste(cols_fusion, collapse = ", ")) else "")

  fusionner <- function(x) {
    v <- trimws(as.character(x))
    v <- unique(v[!is.na(v) & nzchar(v)])
    if (length(v) == 0L) "" else paste(v, collapse = ",")
  }

  # Colonnes stables : on garde la 1re valeur (donc le type d'origine)
  res <- df[, lapply(.SD, data.table::first), by = c(cle), .SDcols = cols_stables]
  if (length(cols_fusion)) {
    res_f <- df[, lapply(.SD, fusionner), by = c(cle), .SDcols = cols_fusion]
    res <- merge(res, res_f, by = cle, sort = FALSE)
    rm(res_f); gc(verbose = FALSE)
  }

  data.table::setcolorder(res, intersect(ordre, names(res)))
  data.table::setDF(res)
  message("[agreger_par_client] ", nrow(df), " lignes -> ", nrow(res),
          " (", cle, " uniques)")
  res
}

# Regroupe les lignes partageant le meme CLIENT en une seule ligne.
# Pour chaque colonne : valeurs distinctes non vides, separees par une virgule.
#   - une seule valeur distincte  -> la valeur telle quelle (type d'origine conserve)
#   - plusieurs valeurs           -> "VAL1,VAL2" (la colonne devient character)
#   - aucune valeur non vide      -> "" (ou NA si la colonne n'est pas character)
# L'ordre d'apparition des CLIENT est conserve (by=, et non keyby= qui trierait).
#   - colonnes de date_cols     -> la date la PLUS ANCIENNE (pas de concatenation),
#                                  reformatee en JJ/MM/AAAA pour rester lisible
#                                  par le dmy() applique plus loin dans le script.
agreger_doublons <- function(df, cle = "CLIENT", date_cols = "DATOUV") {
  if (is.null(df) || nrow(df) == 0 || !(cle %in% names(df))) return(df)

  n_avant <- nrow(df)
  n_cles  <- data.table::uniqueN(df[[cle]])
  if (n_cles == n_avant) {
    message("[agreger_doublons] Aucun ", cle, " en double (", n_avant, " lignes)")
    return(df)
  }

  message("[agreger_doublons] ", n_avant - n_cles, " ligne(s) en trop sur ",
          n_avant, " : regroupement sur ", n_cles, " ", cle, " uniques ...")

  ordre_cols <- names(df)
  dt <- data.table::as.data.table(df)

  # Fusion TOUJOURS en character : data.table impose un type homogene par
  # colonne entre les groupes, or un groupe sans doublon rendrait le type
  # d'origine et un groupe avec doublons du texte -> erreur de type.
  fusion <- function(x) {
    x <- as.character(x)
    u <- unique(x[!is.na(x) & trimws(x) != ""])
    if (length(u) == 0L) return("")
    paste(u, collapse = ",")
  }

  res <- dt[, lapply(.SD, fusion), by = c(cle)]

  # Dates : on ne concatene pas, on garde la PLUS ANCIENNE ouverture du client.
  # Recalcul sur dt (valeurs d'origine) et non sur res, dont la colonne contient
  # deja les dates concatenees par fusion().
  for (dc in intersect(date_cols, names(res))) {
    agg <- dt[, .(..min_d = {
      d <- parse_date_any(get(dc))
      if (all(is.na(d))) NA_character_ else format(min(d, na.rm = TRUE), "%d/%m/%Y")
    }), by = c(cle)]
    # Jointure sur la cle : ne depend pas de l'ordre des lignes.
    idx <- match(res[[cle]], agg[[cle]])
    val <- agg$..min_d[idx]
    val[is.na(val)] <- ""
    data.table::set(res, j = dc, value = val)
  }

  # Retour au type d'origine pour les colonnes qui n'ont finalement subi aucune
  # concatenation : sans cela, des colonnes numeriques (CA, CAPITAL...)
  # deviendraient du texte pour toute la filiale.
  for (nm in setdiff(names(res), cle)) {
    if (!is.character(df[[nm]]) && !any(grepl(",", res[[nm]], fixed = TRUE))) {
      data.table::set(res, j = nm,
                      value = type.convert(res[[nm]], as.is = TRUE))
    }
  }

  data.table::setcolorder(res, intersect(ordre_cols, names(res)))
  data.table::setDF(res)

  message("[agreger_doublons] Termine : ", nrow(res), " lignes")
  res
}

# Excel sheet names must be <= 31 chars and avoid special chars.
safe_sheet_name <- function(name, max_len = 31) {
  if (is.na(name) || !nzchar(name)) name <- "Sheet"
  name <- gsub("[:\\\\/\\?\\*\\[\\]]", " ", name)
  name <- gsub("[\r\n\t]+", " ", name)
  name <- trimws(name)
  if (nchar(name) > max_len) name <- substr(name, 1, max_len)
  if (!nzchar(name)) name <- "Sheet"
  name
}

unique_sheet_name <- function(wb, name) {
  base <- safe_sheet_name(name)
  existing <- tryCatch(openxlsx::getSheetNames(wb), error = function(e) NULL)
  if (is.null(existing) && !is.null(wb$worksheets)) {
    existing <- names(wb$worksheets)
  }
  if (is.null(existing)) return(base)
  candidate <- base
  i <- 1
  while (candidate %in% existing) {
    suffix <- paste0("_", i)
    candidate <- base
    if (nchar(candidate) + nchar(suffix) > 31) {
      candidate <- substr(candidate, 1, 31 - nchar(suffix))
    }
    candidate <- paste0(candidate, suffix)
    i <- i + 1
  }
  candidate
}



#Gestion des couleurs

vert_fonce="#22963B"
vert_clair="#E0F7DC"  
orange="#FFBD0E"
rouge="#F63C00"
bleu="#C2E7FB"

headerStyle <- createStyle(
  fontSize = 14, fontColour = "white", halign = "left",
  fgFill = "#09982E", border = "TopBottom", borderColour = "black"
  )
bonStyle <- createStyle(halign = "left",
fgFill = "#298904"
)
moyenStyle <- createStyle(halign = "left",
fgFill = "#F8DF19"
)
lowStyle <- createStyle(halign = "left",
fgFill = "#D90A0A"
)

  anomStyle <- createStyle(halign = "left",
fgFill = "#FFB65D"
)

## Initiation des tableaux

Sys.setlocale("LC_TIME", "fr_FR.UTF-8")

      cat("ETAPE 1/3: TAUX DE FIABILISATION PAR AGENT \n")


tableau_fiabilisation=data.frame(Flux=c("","Taux de fiabilisation","Appréciation"))
tableau_fiabilisation_stock=data.frame(Stock=c("","Taux de fiabilisation","Appréciation"))

minimum_pp=c()
minimum_pm=c()

fiabilisation_fil=c()
ppt_dg=read_pptx(paste(chemin,"Rapport de suivi.pptx",sep=""))



    # Repartition notation et taux de complétude des agents par intervalle de taux


    notation=read.csv2(paste0(chemin,"notation.csv"), header = FALSE, row.names = NULL)

    colnames(notation)=c("Agent","Filiale","Note","Date_notation")
    
    filiale_note=unique(notation$Filiale)


notation= notation  %>%
    group_by(Filiale, Note) %>%
    summarise(Count = n(), .groups = "drop") %>%
    group_by(Filiale) %>%
    mutate(Percent = Count / sum(Count)) %>%    # proportion (0 à 1)
    mutate(Percent = percent(Percent, accuracy = 0.2)) %>%  # transforme en “xx.x%”
    select(-Count) %>%
    pivot_wider(names_from = Note, values_from = Percent, values_fill = "0%")


  

production = function(fil) {

   # Traitements des données filiales initiales

   ## Clients non fiabilisables

    non_fiab=read.csv2(paste(sep="",chemin,fil,"//data//non_fiab.csv"), fileEncoding = "UTF-8-BOM")
    non_fiab <- clean_colnames(non_fiab)
    non_fiab=as.data.frame(lapply(non_fiab, remove_spaces))

    non_fiab=non_fiab[non_fiab$CODE=="OI",]


# ============================
# 1. Chemin du fichier
# ============================
chemin_pm <- file.path(chemin, fil, "data", "pm_stock.csv")

# Vérification que le fichier existe avant lecture
if (!file.exists(chemin_pm)) {
  stop("Fichier introuvable : ", chemin_pm)
}

# ============================
# 2. Fonction de détection d'encodage (utilisée par read_csv2_auto)
# ============================
detect_encoding <- function(path, n = 100000) {
  raw_sample <- readBin(path, what = "raw", n = n)
  encodings <- stri_enc_detect(raw_sample)
  encoding_detected <- encodings[[1]]$Encoding[1]

  # Sécurité si la détection échoue
  if (is.null(encoding_detected) || is.na(encoding_detected)) {
    encoding_detected <- "UTF-8"
  }

  cat("Encodage retenu :", encoding_detected, "\n")
  encoding_detected
}

# ============================
# 3. Import du CSV
# ============================
# read_csv2_big : lecture rapide fread (multi-thread) + cache .rds,
# gère encodage, espaces parasites, guillemets ; fallback read_csv2_auto
cols_ignorees <- COLONNES_IGNOREES[[fil]]   # NULL si la filiale n'en declare pas

pm_stock <- read_csv2_big(chemin_pm, drop = cols_ignorees)

# Un meme CLIENT peut apparaitre sur plusieurs lignes : on les regroupe des le
# depart, en concatenant par une virgule les valeurs differentes de chaque colonne.
pm_stock <- agreger_doublons(pm_stock, "CLIENT")

dates_triees <- sort(unique(dmy(pm_stock$DATOUV)), decreasing = TRUE)
#premier_jour_mois_courant <- dates_triees[1]+1
#premier_jour_mois_precedent <- dates_triees[1]


## Traitement des PM

if (fil=="ML") {

pm_stock_s=pm_stock

pm_stock_s$CLIENT=as.numeric(pm_stock_s$CLIENT)

risque_s=read.csv2(paste(sep="",chemin,"ML//data//risque.csv"),header=F)
risque_s[,1]=as.numeric(risque_s[,1])
risque=data.frame(CLIENT=risque_s[,1], RISQUE=risque_s[,3])

pm_stock_s=left_join(pm_stock_s,risque, by='CLIENT')



pm_stock_s$RISQUE.x = pm_stock_s$RISQUE.y


pm_stock_s=pm_stock_s[,-which(colnames(pm_stock_s)=="RISQUE.y")]

colnames(pm_stock_s)[which(colnames(pm_stock_s)=="RISQUE.x")] = "RISQUE"

pm_stock_s$RESID[pm_stock_s$PAYS_JUR=="MALI"]="O"
pm_stock_s$RESID[pm_stock_s$PAYS_JUR!="MALI"]="N"

pm_stock = pm_stock_s


} else {
   pm_stock=pm_stock
}




# Vérification
nrow(pm_stock)
colnames(pm_stock)


if ("AGENCE_LIB" %in% names(pm_stock)) {
  colnames(pm_stock)[which(names(pm_stock)=="AGENCE_LIB")] <- "AGENCELIB"

} 

if ("LIB_AGENCE" %in% names(pm_stock)) {
   colnames(pm_stock)[which(names(pm_stock)=="LIB_AGENCE")] <- "AGENCELIB"
}

   
                    
    pm_stock[is.na(pm_stock)]=""

    pm_stock=as.data.frame(lapply(pm_stock, remove_spaces))

    if ("AGENCE" %in% names(pm_stock)) {
        pm_stock$AGENCE <- pad_agence5(pm_stock$AGENCE)
    }

    pm_stock$DATOUV = dmy(pm_stock$DATOUV) 
    
    diff_s=setdiff(pm_stock$CLIENT, non_fiab$CLIENT)

    
    diff_sec_pm=intersect(non_fiab$CLIENT, pm_stock$CLIENT)

    pm_stock= pm_stock[pm_stock$CLIENT %in% diff_s,]

    devise =  data.frame(Filiales=prerequis[,1], Devise=prerequis[,6])

    devise_fil= strsplit(devise[devise$Filiales==fil,2],split=",")

    clients_devise_pm = which(pm_stock$DEVISE %in% devise_fil)

    pm_stock[clients_devise_pm,"DEVISE"]= ""

 

    pm_flux <- pm_stock %>%
    filter(
        DATOUV >= as.Date(premier_jour_mois_precedent),
        DATOUV < as.Date(premier_jour_mois_courant)
    )

  

    cols_vides_pm <- c("AGEC","CODAPE","RCSNO","CAPITAL","CA","RESULTAT","ORIGINE_REVENU","TEL")
    cols_vides_pm <- intersect(cols_vides_pm, names(pm_stock))

    if (length(cols_vides_pm) > 0) {
      pm_stock_f <- pm_stock %>%
        filter(if_any(all_of(cols_vides_pm), ~ is.na(.) | trimws(.) == ""))
    } else {
      pm_stock_f <- pm_stock[0, ]
    }


  

   if (length(cols_vides_pm) > 0) {
     pm_flux_f <- pm_flux %>%
       filter(if_any(all_of(cols_vides_pm), ~ is.na(.) | trimws(.) == ""))
   } else {
     pm_flux_f <- pm_flux[0, ]
   }


     pm_stock   <- dplyr::mutate(pm_stock,   dplyr::across(dplyr::everything(), clean_spaces))
     pm_stock_f <- dplyr::mutate(pm_stock_f, dplyr::across(dplyr::everything(), clean_spaces))
     pm_flux    <- dplyr::mutate(pm_flux,    dplyr::across(dplyr::everything(), clean_spaces))
     pm_flux_f  <- dplyr::mutate(pm_flux_f,  dplyr::across(dplyr::everything(), clean_spaces))




     readr::write_delim(pm_stock,   paste0(chemin,fil,"//data//pm_",fil,"_STOCK.csv"),
                        delim = ";", quote = "all", escape = "double", na = "")
     readr::write_delim(pm_stock_f, paste0(chemin,fil,"//data//pm_",fil,"_STOCK_F.csv"),
                        delim = ";", quote = "all", escape = "double", na = "")
     readr::write_delim(pm_flux,    paste0(chemin,fil,"//data//pm_",fil,".csv"),
                        delim = ";", quote = "all", escape = "double", na = "")
     readr::write_delim(pm_flux_f,  paste0(chemin,fil,"//data//pm_",fil,"_F.csv"),
                        delim = ";", quote = "all", escape = "double", na = "")

    taux_incomp_pm=paste(round(nrow(pm_stock_f)/nrow(pm_stock)*100,1),"%",sep="")

      taux_incomp_pm_f=paste(round(nrow(pm_flux_f)/nrow(pm_flux)*100,1),"%",sep="")

# ============================
# IMPORT PP_STOCK
# ============================
chemin_pp <- file.path(chemin, fil, "data", "pp_stock.csv")

# Vérification que le fichier existe avant lecture
if (!file.exists(chemin_pp)) {
  stop("Fichier introuvable : ", chemin_pp)
}

# Import du CSV
# read_csv2_big : lecture rapide fread (multi-thread) + cache .rds,
# gère encodage, espaces parasites, guillemets ; fallback read_csv2_auto
pp_stock <- read_csv2_big(chemin_pp, drop = cols_ignorees)

# Vérification

## Traitement des PP

if (fil=="ML") {

pp_stock_s=pp_stock

pp_stock_s$CLIENT=as.numeric(pp_stock_s$CLIENT)

risque_s=read.csv2(paste(sep="",chemin,"ML//data//risque.csv"),header=F)
risque_s[,1]=as.numeric(risque_s[,1])
risque=data.frame(CLIENT=risque_s[,1], RISQUE=risque_s[,3])

pp_stock_s=left_join(pp_stock_s,risque, by='CLIENT')



pp_stock_s$RISQUE.x = pp_stock_s$RISQUE.y


pp_stock_s=pp_stock_s[,-which(colnames(pp_stock_s)=="RISQUE.y")]

colnames(pp_stock_s)[which(colnames(pp_stock_s)=="RISQUE.x")] = "RISQUE"

pp_stock_s$RESID[pp_stock_s$PAYS_RESID=="MALI"]="O"
pp_stock_s$RESID[pp_stock_s$PAYS_RESID!="MALI"]="N"

pp_stock = pp_stock_s


} else {
   pp_stock=pp_stock
}



nrow(pp_stock)
colnames(pp_stock)

if ("AGENCE_LIB" %in% names(pp_stock)) {
  colnames(pp_stock)[which(names(pp_stock)=="AGENCE_LIB")] <- "AGENCELIB"

} 

if ("LIB_AGENCE" %in% names(pp_stock)) {
   colnames(pp_stock)[which(names(pp_stock)=="LIB_AGENCE")] <- "AGENCELIB"
}

     # Sous-ensemble utile pour enrichir les anomalies

   ppe_stock <- pp_stock[, c("AGENCE", "AGENCELIB", "CLIENT", "PPE")]
    

     ppe_stock=ppe_stock[ppe_stock$PPE=="O",]
  

    
    pp_stock <- clean_colnames(pp_stock)
    
    pp_stock[is.na(pp_stock)]=""
    
    cli_nul=which(pp_stock$CLIENT=="")
    if (length(cli_nul)!=0) {
        pp_stock=pp_stock[-cli_nul,]
    } else {
        pp_stock=pp_stock
    }
    
     pp_stock=as.data.frame(lapply(pp_stock, remove_spaces))

     if ("AGENCE" %in% names(pp_stock)) {
        pp_stock$AGENCE <- pad_agence5(pp_stock$AGENCE)
     }
    
    pp_stock$DATOUV = dmy(pp_stock$DATOUV)

    diff=setdiff(pp_stock$CLIENT, non_fiab$CLIENT)

    
    diff_sec_pp=intersect(non_fiab$CLIENT, pp_stock$CLIENT)

    pp_stock= pp_stock[pp_stock$CLIENT %in% diff,]
    
    
    clients_devise_pp = which(pp_stock$DEVISE %in% devise_fil)

    pp_stock[clients_devise_pp,"DEVISE"]= ""


    pp_flux <- pp_stock %>%
    filter(
        DATOUV >= as.Date(premier_jour_mois_precedent),
        DATOUV < as.Date(premier_jour_mois_courant)
    )


 cols_vides_pp <- c("CODAPE","PAYNAIS","DATNAIS","PROFESSION","ADRESSE","PAYS_RESID",
                    "NUMID","SALAIRE","ORIGINE_REVENU","DATVALID","TEL")
 cols_vides_pp <- intersect(cols_vides_pp, names(pp_stock))

 if (length(cols_vides_pp) > 0) {
   pp_stock_f <- pp_stock %>%
     filter(if_any(all_of(cols_vides_pp), ~ is.na(.) | trimws(.) == ""))
 } else {
   pp_stock_f <- pp_stock[0, ]
 }


  

   if (length(cols_vides_pp) > 0) {
     pp_flux_f <- pp_flux %>%
       filter(if_any(all_of(cols_vides_pp), ~ is.na(.) | trimws(.) == ""))
   } else {
     pp_flux_f <- pp_flux[0, ]
   }


     pp_stock   <- dplyr::mutate(pp_stock,   dplyr::across(dplyr::everything(), clean_spaces))
     pp_flux    <- dplyr::mutate(pp_flux,    dplyr::across(dplyr::everything(), clean_spaces))
     pp_stock_f <- dplyr::mutate(pp_stock_f, dplyr::across(dplyr::everything(), clean_spaces))
     pp_flux_f  <- dplyr::mutate(pp_flux_f,  dplyr::across(dplyr::everything(), clean_spaces))



     readr::write_delim(pp_stock, paste0(chemin,fil,"//data//pp_",fil,"_STOCK.csv"),
                        delim = ";", quote = "all", escape = "double", na = "")
     readr::write_delim(pp_flux, paste0(chemin,fil,"//data//pp_",fil,".csv"),
                        delim = ";", quote = "all", escape = "double", na = "")

     readr::write_delim(pp_stock_f, paste0(chemin,fil,"//data//pp_",fil,"_STOCK_F.csv"),
                        delim = ";", quote = "all", escape = "double", na = "")
     readr::write_delim(pp_flux_f, paste0(chemin,fil,"//data//pp_",fil,"_F.csv"),
                        delim = ";", quote = "all", escape = "double", na = "")

    taux_incomp_pp=paste(round(nrow(pp_stock_f)/nrow(pp_stock)*100,1),"%",sep="")
    taux_incomp_pp_f=paste(round(nrow(pp_flux_f)/nrow(pp_flux)*100,1),"%",sep="")



  #Archivage
          # Liste des fichiers dans le dossier (sans le chemin complet)

      repertoire=file.path(chemin,fil,"Archives")
      dir.create(repertoire)
      fichiers_dossier <- list.files(paste0(chemin,fil), full.names = FALSE)

      # Spécifiez les mots-clés à chercher
      mots_cles <- c("contrôle","suivi","data","Archives")

      # Filtrer les fichiers à conserver
      fichiers_a_conserver <- fichiers_dossier[
        grepl(paste(mots_cles, collapse = "|"), fichiers_dossier)
      ]

      # Fichiers à archiver (sans chemins absolus)
      fichiers_a_archiver <- setdiff(fichiers_dossier, fichiers_a_conserver)

      if (length(fichiers_a_archiver)!=0) {
          repertoire=paste0(chemin,fil,"//",fichiers_a_archiver)
      zipr(paste0(chemin,fil,"//Archives","//Archives ",fil," _ ",premier_jour_mois_precedent,".zip"), repertoire)

          unlink(repertoire, recursive = TRUE)
          }


     repertoire=file.path(chemin,"Images")
     dir.create(repertoire)
     sigle=paste("BOA_",fil, sep="")
  
         ## les fichiers excel
     cp_flux=read.csv2(paste(sep="",chemin,fil,"//contrôle qualité_CP_Flux.csv"), fileEncoding = "UTF-8-BOM")
     cp_flux <- clean_colnames(cp_flux)
          cp_flux$Agents=as.character(cp_flux$Agents)


     cp_stock=read.csv2(paste(sep="",chemin,fil,"//contrôle qualité_CP_Stock.csv"), fileEncoding = "UTF-8-BOM")
     cp_stock <- clean_colnames(cp_stock)
          cp_stock$Agents=as.character(cp_stock$Agents)

     zone=read.csv2(paste(sep="",chemin,"zone_",fil,".csv"), fileEncoding = "UTF-8-BOM")
     zone <- clean_colnames(zone)

     zone$AGENCE=as.numeric(zone$AGENCE)
     ppt=read_pptx(paste(chemin,"Temp rapport suivi.pptx",sep=""))
    
   
      
            


#####-----------------------DONNEES PAR AGENCE-------------###########
      cat("######################################################\n")
      cat("######### ETAPE 1: TAUX DE FIABILISATION PAR AGENCE \n")
      cat("#####################################################\n")


taux_function_pp=function(x) {

            if (exploitant=="agent") {
                 expl=pp_ne[pp_ne$EXPL==x,]
            } else {
                expl=pp_ne[pp_ne$AGENCE==x,]
            }

            n_expl_s=expl[expl$PAYNAIS %in% inc  | is.na(expl$PAYNAIS)=="TRUE" | expl$PROFESSION %in% inc  | is.na(expl$PROFESSION)=="TRUE"
                    | expl$SALAIRE %in% inc  | is.na(expl$SALAIRE)=="TRUE" | expl$CODAPE %in% inc  | is.na(expl$CODAPE)=="TRUE" 
                    | expl$TEL %in% inc  | is.na(expl$TEL)=="TRUE" | expl$ADRESSE %in% inc  | is.na(expl$ADRESSE) | expl$NUMID %in% inc  | is.na(expl$NUMID)=="TRUE" | expl$DATNAIS %in% inc  | is.na(expl$DATNAIS)=="TRUE" | expl$DATVALID %in% inc  | is.na(expl$DATVALID)=="TRUE" | expl$ORIGINE_REV %in% inc  | is.na(expl$ORIGINE_REV)=="TRUE"  ,]
            n_cons=length(unique(n_expl_s$CLIENT))  
            
                a=field_completion_rate(expl, "PAYNAIS", inc)
                b=field_completion_rate(expl, "PROFESSION", inc)
                c=field_completion_rate(expl, "SALAIRE", inc)
                d=field_completion_rate(expl, "CODAPE", inc)
                e=field_completion_rate(expl, "TEL", inc)
                f=field_completion_rate(expl, "ADRESSE", inc)
                g=field_completion_rate(expl, "NUMID", inc)
                h=field_completion_rate(expl, "DATNAIS", inc)
                i=field_completion_rate(expl, "DATVALID", inc)
                j=field_completion_rate(expl, "ORIGINE_REVENU", inc)

                taux=min_rate(a,b,c,d,e,f,g,h,i,j)
                appreciation=get_appreciation(taux, Faible, Moyen)

                #if (taux_rat<0) {
                #taux_ratt= paste("En avance de + ",abs(taux_rat),"%", sep="")
                #} else {
                #taux_ratt= paste("En retard de ",taux_rat,"%", sep="")
                #}

                taux=format_percent(taux)
                lieu_naiss=format_percent(a)
                profession=format_percent(b)
                revenu=format_percent(c)
                codape=format_percent(d)
                tel=format_percent(e)
                adresse=format_percent(f)
                nin=format_percent(g)
                datnais=format_percent(h)
                datvalid=format_percent(i)
                origine=format_percent(j)


              if (exploitant=="agent") {
                    etat_expls=data.frame(Agents=x,`Nbre clients concernés`=n_cons,`Lieu de Naissance`=lieu_naiss, Profession =profession, Codape=codape, Revenu = revenu, NIN=nin, TEL=tel,Adresse=adresse,DATNAIS=datnais, DATVALID=datvalid, Origine_Revenu=origine, `Taux de fiabilisation`=taux, Appréciation=appreciation) # ##, `Taux à rattrapper`=taux_ratt)
            
              } else {
                    etat_expls=data.frame(Agence=x,`Nbre clients concernés`=n_cons,`Lieu de Naissance`=lieu_naiss, Profession =profession, Codape=codape, Revenu = revenu, NIN=nin, TEL=tel,Adresse=adresse,DATNAIS=datnais, DATVALID=datvalid, Origine_Revenu=origine, `Taux de fiabilisation`=taux, Appréciation=appreciation) # ##, `Taux à rattrapper`=taux_ratt)

              }

              colnames(etat_expl)=colnames(etat_expls)
              etat_filiale = rbind(etat_expl,etat_expls)
            }


        

        taux_function_pm=function(x) {
            if (exploitant=="agent") {
                 expl=pm_ne[pm_ne$EXPL==x,]
            } else {
                expl=pm_ne[pm_ne$AGENCE==x,]
            }
            
                n_expl=expl[expl$AGEC %in% inc  | is.na(expl$AGEC)=="TRUE" | expl$CAPITAL %in% inc  | is.na(expl$CAPITAL)=="TRUE" | expl$CA %in% inc  | is.na(expl$CA)=="TRUE" | 
                expl$RESULTAT %in% inc  | is.na(expl$RESULTAT)=="TRUE" | expl$RCSNO %in% inc  | is.na(expl$RCSNO)=="TRUE" |
                expl$CODAPE %in% inc  | is.na(expl$CODAPE)=="TRUE" |
                expl$ORIGINE_REV %in% inc  | is.na(expl$ORIGINE_REV)=="TRUE" |
                expl$TEL %in% inc  | is.na(expl$TEL)=="TRUE" ,] 


             
            
            n_cons=length(unique(n_expl$CLIENT))

         
       
            
                    a=field_completion_rate(expl, "CAPITAL", inc)
                    b=field_completion_rate(expl, "CA", inc)
                    c=field_completion_rate(expl, "RESULTAT", inc)
                    d=field_completion_rate(expl, "RCSNO", inc)
                    e=field_completion_rate(expl, "CODAPE", inc)
                    f=field_completion_rate(expl, "AGEC", inc)
                    g=field_completion_rate(expl, "ORIGINE_REVENU", inc)
                    h=field_completion_rate(expl, "TEL", inc)

                    taux=min_rate(a,b,c,d,e,f,g,h)
                    appreciation=get_appreciation(taux, Faible, Moyen)
                    taux_ratt=get_taux_ratt(taux, trimestre)

                    taux=format_percent(taux)
                    capital=format_percent(a)
                    ca=format_percent(b)
                    resultat=format_percent(c)
                    rcsno=format_percent(d)
                    codape=format_percent(e)

                    agec=format_percent(f)
                    origine=format_percent(g)
                    tel=format_percent(h)

                    if (exploitant=="agent") {
                        etat_expls=data.frame(Agents=x,`Nbre clients concernés`=n_cons,AGEC=agec,`Capital`=capital, CA = ca, Resultat = resultat, RCSNO = rcsno,CODAPE= codape, Origine_Revenu=origine, TEL=tel,`Taux de fiabilisation`=taux, Appréciation=appreciation) # ##, `Taux à rattrapper`=taux_ratt)
                    } else {
                        etat_expls=data.frame(Agence=x,`Nbre clients concernés`=n_cons,AGEC=agec, `Capital`=capital, CA = ca, Resultat = resultat, RCSNO = rcsno,CODAPE= codape, Origine_Revenu=origine, TEL=tel, `Taux de fiabilisation`=taux, Appréciation=appreciation) # ##, `Taux à rattrapper`=taux_ratt)
                    }

                    colnames(etat_expls)=colnames(etat_expl)

                    etat_filiale = rbind(etat_expl,etat_expls)
            }
        #function_kyc= function(fil){
        

          
          
          tableau_suivi=data.frame(Flux=c("","Taux de fiabilisation","Appréciation"))
          tableau_suivi_stock=data.frame(Stock=c("","Taux de fiabilisation","Appréciation"))
          
          
          sigle=paste("BOA_",fil, sep="")
          
       
            
            cat("######################################################\n")
            cat("######### Chargement des données de\n",sigle, "#######\n")
            cat("#####################################################\n")
            # Importatations des donnees
          
            # pp_flux/pm_flux sont déjà en mémoire (dérivés de pp_stock/pm_stock),
            # inutile de relire les CSV qui viennent d'être écrits
            pp_ne <- pp_flux
            pp_ne$AGENCE=as.numeric(pp_ne$AGENCE)


            pp_ne=select_pp_fields(pp_ne, pp_fields)

            colnames(pp_ne)=toupper(colnames(pp_ne))
            pm_ne <- pm_flux
            pm_ne$AGENCE=as.numeric(pm_ne$AGENCE)



            pm_ne=select_pm_fields(pm_ne, pm_fields)

            colnames(pm_ne)=toupper(colnames(pm_ne))
                
             pp_ne$EXPL[is_alphanumeric(pp_ne$EXPL)=="FALSE"]=paste("DIR_AGENCE_",pp_ne$AGENCE[is_alphanumeric(pp_ne$EXPL)=="FALSE"],sep="")
             pm_ne$EXPL[is_alphanumeric(pm_ne$EXPL)=="FALSE"]=paste("DIR_AGENCE_",pm_ne$AGENCE[is_alphanumeric(pm_ne$EXPL)=="FALSE"],sep="")



            pp_ne <- clean_and_mark_anomalies(pp_ne, start_col = 4)
            pm_ne <- clean_and_mark_anomalies(pm_ne, start_col = 4)


            if (exists("pp_ne")=="TRUE" & exists("pm_ne")=="TRUE") {
              
              cat("########################################################################\n")
              cat("######### Les données de\n",sigle, "ont été chargées avec succès #######\n")
              cat("########################################################################\n")
              
            } else {
              
              cat("################################################################################################\n")
              cat("######### Erreur: les données de\n",sigle, "n'ont pas été bien chargées (Voir les formats) #####\n")
              cat("###############################################################################################\n")
              
            }
            
            
            
            
            ## Appreciation flux
            
            trimestre=100
            Faible=80
            Moyen=100
            Bon=100
            
            ## Statistique a l'échelle filiale (PP)
       
        a=field_completion_rate(pp_ne, "PAYNAIS", inc)
        b=field_completion_rate(pp_ne, "PROFESSION", inc)
        c=field_completion_rate(pp_ne, "SALAIRE", inc)
        d=field_completion_rate(pp_ne, "CODAPE", inc)
        e=field_completion_rate(pp_ne, "TEL", inc)
        f=field_completion_rate(pp_ne, "ADRESSE", inc)
        g=field_completion_rate(pp_ne, "NUMID", inc)
        h=field_completion_rate(pp_ne, "DATNAIS", inc)
        i=field_completion_rate(pp_ne, "DATVALID", inc)
        j=field_completion_rate(pp_ne, "ORIGINE_REVENU", inc)
        


        T=length(c(a,b,c,d,e,f,g,h,i,j))
        
       
                    
      #  taux=floor(100*(1-sum(nrow(pp_ne[pp_ne$PAYNAIS=="" | is.na(pp_ne$PAYNAIS)=="TRUE",]),nrow(pp_ne[pp_ne$PROFESSION=="" | is.na(pp_ne$PROFESSION)=="TRUE",]),
      #           nrow(pp_ne[pp_ne$SALAIRE=="" | is.na(pp_ne$SALAIRE)=="TRUE",]), nrow(pp_ne[pp_ne$NUMID=="" | is.na(pp_ne$NUMID)=="TRUE",]),
      #           nrow(pp_ne[pp_ne$CODAPE=="" | is.na(pp_ne$CODAPE)=="TRUE",]),nrow(pp_ne[pp_ne$TEL=="" | is.na(pp_ne$TEL)=="TRUE",]),          
      #           nrow(pp_ne[pp_ne$DATNAIS=="" | is.na(pp_ne$DATNAIS)=="TRUE",]),
      #           nrow(pp_ne[pp_ne$ADRESSE=="" |is.na(pp_ne$ADRESSE)=="TRUE",]),   nrow(pp_ne[pp_ne$NUMID=="" |is.na(pp_ne$NUMID)=="TRUE",]), nrow(pp_ne[pp_ne$DATVALID=="" |is.na(pp_ne$DATVALID)=="TRUE" ,]), 
      #                     nrow(pp_ne[pp_ne$ORIGINE_REV=="" |is.na(pp_ne$ORIGINE_REV)=="TRUE" ,])
      #           
      #           )/(T*nrow(pp_ne))))
      # 

       
       
        champs=c("PAYNAIS","PROFESSION","SALAIRE","NUMID","CODAPE","TEL","DATNAIS","ADRESSE","DATVALID","ORIGINE_REVENU")

        taux=compute_taux(pp_ne, champs)
        appreciation=get_appreciation(taux, Faible, Moyen)
        taux_ratt=get_taux_ratt(taux, trimestre)
        taux=format_percent(taux)

        lieu_naiss=format_percent(a)
        profession=format_percent(b)
        revenu=format_percent(c)
        codape=format_percent(d)
        tel=format_percent(e)
        adresse=format_percent(f)
        nin=format_percent(g)
        datnais=format_percent(h)
        datvalid=format_percent(i)
        origine=format_percent(j)



       
        etat_pp_nes=data.frame(`Lieu de Naissance` = lieu_naiss, Profession = profession,Codape=codape, Revenu = revenu, NIN = nin, TEL=tel, Adresse=adresse,DATNAIS=datnais,DATVALID=datvalid, ORIGINE_REV=origine, `Taux de fiabilisation` =taux, Appréciation=appreciation, `Taux à rattrapper` = taux_ratt)
            pp=etat_pp_nes[,c(ncol(etat_pp_nes),ncol(etat_pp_nes)-1,ncol(etat_pp_nes)-2)]
            pp_t=data.frame(A="",V="")
            
            colnames(pp_t)=c(paste(fil),"")
            pp_t[1,]=c("PM","PP")
            pp_t[2,2]=c(pp[1,c(3)])
            pp_t[3,2]=c(pp[1,c(2)])
            
            rownames(pp_t)=c("","Taux de fiabilisation","Appréciation")
            ## Statistique a l'échelle filiale (PM)
            

            
            a=field_completion_rate(pm_ne, "CAPITAL", inc)
            b=field_completion_rate(pm_ne, "CA", inc)
            c=field_completion_rate(pm_ne, "RESULTAT", inc)
            d=field_completion_rate(pm_ne, "RCSNO", inc)
            e=field_completion_rate(pm_ne, "CODAPE", inc)
            f=field_completion_rate(pm_ne, "AGEC", inc)
            g=field_completion_rate(pm_ne, "ORIGINE_REVENU", inc)
            h=field_completion_rate(pm_ne, "TEL", inc)

           
            K=length(c(a,b,c,d,e,f,g,h))

         #   taux=floor(100*(1-sum(nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC)=="TRUE",]), nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",]), nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",]),
         #
              #nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",]), nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),]),
         #
             # nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),]), nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc | is.na(pm_ne$ORIGINE_REV)=="TRUE",]), nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL)=="TRUE",]))/(K*nrow(pm_ne))))
#

        champs=c("CAPITAL","CA","RESULTAT","RCSNO","CODAPE","AGEC","ORIGINE_REVENU","TEL")

        taux=compute_taux(pm_ne, champs)
        appreciation=get_appreciation(taux, Faible, Moyen)
        taux_ratt=get_taux_ratt(taux, trimestre, label_retard = FALSE)
        taux=format_percent(taux)
        capital=format_percent(a)
        ca=format_percent(b)
        resultat=format_percent(c)
        rcsno=format_percent(d)
        codape=format_percent(e)
        agec=format_percent(f)
        origine=format_percent(g)
        tel=format_percent(h)


            
            etat_pm_nes=data.frame(AGEC=agec,`Capital`=capital, CA = ca, Resultat = resultat, RCSNO = rcsno,CODAPE= codape,  ORIGINE_REV=origine, TEL=tel, `Taux de fiabilisation`=taux, Appréciation=appreciation) # ##, `Taux à rattrapper`=taux_ratt)
            
            
            pm=etat_pm_nes[,c(ncol(etat_pm_nes),ncol(etat_pm_nes)-1,ncol(etat_pm_nes)-2)]
            
            pp_t[2,1]=c(pm[1,c(2)])
            pp_t[3,1]=c(pm[1,c(1)])

            tableau_suivi = cbind(tableau_suivi,pp_t)
            tableau_suivi[,1]=rownames(tableau_suivi)
            
            ## PP
            
            agents=unique(pp_ne$AGENCE)#("[[:alnum:]]", pp_ne$EXPL)=="TRUE"])
            #agents_null_pp=pp_ne[grepl("[[:alnum:]]", pp_ne$EXPL)=="FALSE",]

            exploitant="agence"
            

            etat_expl=data.frame(Agence="",`Nbre clients concernés`="",`Lieu de Naissance`="", Profession = "",Codape="", Revenu = "", NIN="", Tel="",Adresse="",DATNAIS="", DATVALID="", ORIGINE_REV="", `Taux de fiabilisation`="", Appréciation="") # ##, `Taux à rattrapper`="")
             taux_filiale = lapply(agents,taux_function_pp)
            
            taux_filiale_t=bind_results(taux_filiale, etat_expl)
            taux_filiale_t=taux_filiale_t[-which(taux_filiale_t$NIN==""),]
            
      
     
            ## PM
            
            agents_pm=unique(pm_ne$AGENCE)#("[[:alnum:]]", pm_ne$EXPL)=="TRUE"])
            #agents_null_pm=pm_ne[grepl("[[:alnum:]]", pm_ne$EXPL)=="FALSE",]
            
          
            
            etat_expl=data.frame(Agence="",`Nbre clients concernés`="", AGEC="", Capital="", CA = "", Resultat = "", RCSNO = "", CODAPE= "",  ORIGINE_REV=origine, TEL=tel,  `Taux de fiabilisation`="", Appréciation="")#,  `Taux à rattrapper`="")

            taux_filiale_pm = lapply(agents_pm,taux_function_pm)
            
            taux_filiale_pm=bind_results(taux_filiale_pm, etat_expl)
            taux_filiale_pm=taux_filiale_pm[-which(taux_filiale_pm$RCSNO==""),]
            
         
               
            
            rm(pp_ne,pm_ne)
            
            
            ### LE stock
            
            cat("######################################################\n")
            cat("######### Chargement des données Stock de\n",sigle, "#######\n")
            cat("#####################################################\n")
            # Importatations des donnees

            # pp_stock/pm_stock sont déjà en mémoire et nettoyés,
            # inutile de relire les CSV _STOCK qui viennent d'être écrits
            pp_ne <- pp_stock
            pp_ne$AGENCE=as.numeric(pp_ne$AGENCE)




            pp_ne=select_pp_fields(pp_ne, pp_fields)

            colnames(pp_ne)=toupper(colnames(pp_ne))
            pm_ne <- pm_stock
            pm_ne$AGENCE=as.numeric(pm_ne$AGENCE)


            pm_ne=select_pm_fields(pm_ne, pm_fields)
            colnames(pm_ne)=toupper(colnames(pm_ne))


                
            pp_ne$EXPL[is_alphanumeric(pp_ne$EXPL)=="FALSE"]=paste("DIR_AGENCE_",pp_ne$AGENCE[is_alphanumeric(pp_ne$EXPL)=="FALSE"],sep="")
            pm_ne$EXPL[is_alphanumeric(pm_ne$EXPL)=="FALSE"]=paste("DIR_AGENCE_",pm_ne$AGENCE[is_alphanumeric(pm_ne$EXPL)=="FALSE"],sep="")


            pp_ne <- clean_and_mark_anomalies(pp_ne, start_col = 4)
            pm_ne <- clean_and_mark_anomalies(pm_ne, start_col = 4)


            if (exists("pp_ne")=="TRUE" & exists("pm_ne")=="TRUE") {
              
              cat("########################################################################\n")
              cat("######### Les données Stock de\n",sigle, "ont été chargées avec succès #######\n")
              cat("########################################################################\n")
              
            } else {
              
              cat("################################################################################################\n")
              cat("######### Erreur: les données Stock de\n",sigle, "n'ont pas été bien chargées (Voir les formats) #####\n")
              cat("###############################################################################################\n")
              
            }


            
            
            ##-----Appréciation du Stock-####
            
            if (trimestre_actuel=="1"){
              trimestre=30
              Faible=5
              Moyen=30
              
            } else if (trimestre_actuel=="2") {
              trimestre=60
              Faible=30
              Moyen=60
            }  else if (trimestre_actuel=="3") {
              trimestre=90
              Faible=60
              Moyen=90
            }  else {
              trimestre=95
              Faible=65
              Moyen=95
            }
            
            
            
            ## Statistique a l'échelle filiale (PP)
            
        a=field_completion_rate(pp_ne, "PAYNAIS", inc)
        b=field_completion_rate(pp_ne, "PROFESSION", inc)
        c=field_completion_rate(pp_ne, "SALAIRE", inc)
        d=field_completion_rate(pp_ne, "CODAPE", inc)
        e=field_completion_rate(pp_ne, "TEL", inc)
        f=field_completion_rate(pp_ne, "ADRESSE", inc)
        g=field_completion_rate(pp_ne, "NUMID", inc)
        h=field_completion_rate(pp_ne, "DATNAIS", inc)
        i=field_completion_rate(pp_ne, "DATVALID", inc)
        j=field_completion_rate(pp_ne, "ORIGINE_REVENU", inc)

        T=length(c(a,b,c,d,e,f,g,h,i,j))
        
       
               
       #taux=floor(100*(1-sum(nrow(pp_ne[pp_ne$PAYNAIS=="" | is.na(pp_ne$PAYNAIS)=="TRUE",]),nrow(pp_ne[pp_ne$PROFESSION=="" | is.na(pp_ne$PROFESSION)=="TRUE",]),
       #         nrow(pp_ne[pp_ne$SALAIRE=="" | is.na(pp_ne$SALAIRE)=="TRUE",]), nrow(pp_ne[pp_ne$NUMID=="" | is.na(pp_ne$NUMID)=="TRUE",]),
       #         nrow(pp_ne[pp_ne$CODAPE=="" | is.na(pp_ne$CODAPE)=="TRUE",]),nrow(pp_ne[pp_ne$TEL=="" | is.na(pp_ne$TEL)=="TRUE",]),          
       #         nrow(pp_ne[pp_ne$DATNAIS=="" | is.na(pp_ne$DATNAIS)=="TRUE",]),
       #         nrow(pp_ne[pp_ne$ADRESSE=="" |is.na(pp_ne$ADRESSE)=="TRUE",]),   nrow(pp_ne[pp_ne$NUMID=="" |is.na(pp_ne$NUMID)=="TRUE",]), nrow(pp_ne[pp_ne$DATVALID=="" |is.na(pp_ne$DATVALID)=="TRUE",]), 
       #                   nrow(pp_ne[pp_ne$ORIGINE_REV=="" |is.na(pp_ne$ORIGINE_REV)=="TRUE",])
       #         
       #         )/(T*nrow(pp_ne))))
       #

       
       
        champs=c("PAYNAIS","PROFESSION","SALAIRE","NUMID","CODAPE","TEL","DATNAIS","ADRESSE","DATVALID","ORIGINE_REVENU")

        taux=compute_taux(pp_ne, champs)
        appreciation=get_appreciation(taux, Faible, Moyen)
        taux_ratt=get_taux_ratt(taux, trimestre)
        taux=format_percent(taux)

        lieu_naiss=format_percent(a)
        profession=format_percent(b)
        revenu=format_percent(c)
        codape=format_percent(d)
        tel=format_percent(e)
        adresse=format_percent(f)
        nin=format_percent(g)
        datnais=format_percent(h)
        datvalid=format_percent(i)
        origine=format_percent(j)



        etat_pp_nes=data.frame(`Lieu de Naissance` = lieu_naiss, Profession = profession,Codape=codape, Revenu = revenu, NIN = nin, TEL=tel, Adresse=adresse,DATNAIS=datnais, DATVALID=datvalid,ORIGINE_REV=origine, `Taux de fiabilisation` =taux, Appréciation=appreciation, `Taux à rattrapper` = taux_ratt)
        pp=etat_pp_nes[,c(ncol(etat_pp_nes),ncol(etat_pp_nes)-1,ncol(etat_pp_nes)-2)]
        pp_t=data.frame(A="",V="")
            
            colnames(pp_t)=c(paste(fil),"")
            pp_t[1,]=c("PM","PP")
            pp_t[2,2]=c(pp[1,c(3)])
            pp_t[3,2]=c(pp[1,c(2)])
            
            rownames(pp_t)=c("","Taux de fiabilisation","Appréciation")
            
            ## Statistique a l'échelle filiale (PM)
                     
            a=field_completion_rate(pm_ne, "CAPITAL", inc)
            b=field_completion_rate(pm_ne, "CA", inc)
            c=field_completion_rate(pm_ne, "RESULTAT", inc)
            d=field_completion_rate(pm_ne, "RCSNO", inc)
            e=field_completion_rate(pm_ne, "CODAPE", inc)
            f=field_completion_rate(pm_ne, "AGEC", inc)
            g=field_completion_rate(pm_ne, "ORIGINE_REVENU", inc)
            h=field_completion_rate(pm_ne, "TEL", inc)

           
            K=length(c(a,b,c,d,e,f,g,h))

          #  taux=floor(100*(1-sum(nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC)=="TRUE",]), nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",]), nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",]),
          #    nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",]), nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),]),
          #    nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),]), nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc | is.na(pm_ne$ORIGINE_REV)=="TRUE",]), nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL)=="TRUE",]))/(K*nrow(pm_ne))))
#
        champs=c("CAPITAL","CA","RESULTAT","RCSNO","CODAPE","AGEC","ORIGINE_REVENU","TEL")

        taux=compute_taux(pm_ne, champs)
        appreciation=get_appreciation(taux, Faible, Moyen)
        taux_ratt=get_taux_ratt(taux, trimestre, label_retard = FALSE)
        taux=format_percent(taux)
        capital=format_percent(a)
        ca=format_percent(b)
        resultat=format_percent(c)
        rcsno=format_percent(d)
        codape=format_percent(e)
        agec=format_percent(f)
        origine=format_percent(g)
        tel=format_percent(h)


            
            etat_pm_nes=data.frame(AGEC=agec,`Capital`=capital, CA = ca, Resultat = resultat, RCSNO = rcsno,CODAPE= codape,  ORIGINE_REV=origine, TEL=tel, `Taux de fiabilisation`=taux, Appréciation=appreciation) # ##, `Taux à rattrapper`=taux_ratt)
            
            
            pm=etat_pm_nes[,c(ncol(etat_pm_nes),ncol(etat_pm_nes)-1,ncol(etat_pm_nes)-2)]
            
           pp_t[2,1]=c(pm[1,c(2)])
            pp_t[3,1]=c(pm[1,c(1)])
            
            tableau_suivi_stock = cbind(tableau_suivi_stock,pp_t)
            tableau_suivi_stock[,1]=rownames(tableau_suivi_stock)
            
            tableau_fiabilisation_stock=cbind(tableau_fiabilisation_stock, tableau_suivi_stock)
            
            if (exists("tableau_fiabilisation_stock")=="TRUE") {
              cat("######################################################################################\n")
              cat("######### Les fichiers Stock des suivi de ",sigle," par agence sont générés avec sucès ######\n")
              cat("######################################################################################\n")
            } else {
              cat("######################################################################################\n")
              cat("######### ERREUR: Les fichiers Stock de suivi de ",sigle," par agence ne sont pas générés ####\n")
              cat("######################################################################################\n")
              
            }
            
            exploitant="agence"
            
            ## PP
            
            agents=unique(pp_ne$AGENCE)            
            
            etat_expl=data.frame(Agence="",`Nbre clients concernés`="", `Lieu de Naissance`= "", Profession = "",Codape="", Revenu = "", NIN= "",  Tel="" ,Adresse="",DATNAIS="", DATVALID="",  ORIGINE_REV="",`Taux de fiabilisation`="", Appréciation="") # ##, `Taux à rattrapper`="")
             taux_filiale = lapply(agents,taux_function_pp)

            taux_filiale_t_stock=bind_results(taux_filiale, etat_expl)
            taux_filiale_t_stock=taux_filiale_t_stock[-which(taux_filiale_t_stock$NIN==""),]
  
            
            
   
            
            ## PM
            
            agents_pm=unique(pm_ne$AGENCE)#("[[:alnum:]]", pm_ne$EXPL)=="TRUE"])
            #agents_null_pm=pm_ne[grepl("[[:alnum:]]", pm_ne$EXPL)=="FALSE",]
            

            etat_expl=data.frame(Agence="", `Nbre clients concernés`="",AGEC="", Capital="", CA = "", Resultat = "", RCSNO = "",CODAPE= "", ORIGINE_REV="", TEL=tel,  `Taux de fiabilisation`="", Appréciation="")#,  `Taux à rattrapper`="")
            taux_filiale_pm_stock = lapply(agents_pm,taux_function_pm)
            
            taux_filiale_pm_stock=bind_results(taux_filiale_pm_stock, etat_expl)
            taux_filiale_pm_stock=taux_filiale_pm_stock[-which(taux_filiale_pm_stock$RCSNO==""),]
            
      
            
            
            ### Creation du fichier Excel de suivi
            wb=createWorkbook()
            
    
            
            ### Resume filiale
            addWorksheet(wb,"Récapitulatif")
            
            
            k=ncol(tableau_suivi)
    
            ### recap stock
            colnames(tableau_suivi_stock)=c("Stock",fil,"")
            tableau_suivi_stock_t=tableau_suivi_stock[-3,]
            writeData(wb,"Récapitulatif", x=tableau_suivi_stock_t, startRow=5, startCol=3)
            addStyle(wb,"Récapitulatif",headerStyle,cols=3:5, rows=5)
            
            ### recap flux
            colnames(tableau_suivi)=c("Flux",fil,"")
            tableau_suivi_t=tableau_suivi[-3,]
            writeData(wb,"Récapitulatif", x=tableau_suivi_t, startRow=5, startCol=7)
            addStyle(wb,"Récapitulatif",headerStyle,cols=7:9, rows=5)
  
            
            
            
            ### Sheet Flux PP
            addWorksheet(wb,"Flux PP")
            
            
            writeData(wb,"Flux PP", x=taux_filiale_t, startRow=1, startCol=1)
            
            k=ncol(taux_filiale_t)
            
           
            addStyle(wb,"Flux PP",headerStyle,cols=1:k, rows=1)
            

                             
            apply_status_style(wb, "Flux PP", taux_filiale_t, value_col = 14)
            
            ### Sheet Flux PM
            addWorksheet(wb,"Flux PM")
            
            writeData(wb,"Flux PM", x=taux_filiale_pm, startRow=1, startCol=1)
            
            k=ncol(taux_filiale_pm)
            
           
            
            addStyle(wb,"Flux PM",headerStyle,cols=1:k, rows=1)
            
            
            apply_status_style(wb, "Flux PM", taux_filiale_pm, value_col = 12)
            
            
            
            ### Sheet Stock PP
            addWorksheet(wb,"Stock PP")
            
            
            writeData(wb,"Stock PP", x=taux_filiale_t_stock, startRow=1, startCol=1)
            
            k=ncol(taux_filiale_t_stock)
            
         
            
            addStyle(wb,"Stock PP",headerStyle,cols=1:k, rows=1)
            

            apply_status_style(wb, "Stock PP", taux_filiale_t_stock, value_col = 14)
            
            ### Sheet Stock PM
            addWorksheet(wb,"Stock PM")
            
            writeData(wb,"Stock PM", x=taux_filiale_pm_stock, startRow=1, startCol=1)
            
            k=ncol(taux_filiale_pm_stock)
            
       
            
            addStyle(wb,"Stock PM",headerStyle,cols=1:k, rows=1)
            
            
            apply_status_style(wb, "Stock PM", taux_filiale_pm_stock, value_col = 12)
            
            saveWorkbook(wb, paste(sep="",paste(chemin,fil,"//",sep=""),"Rapport du taux de complétude par agence ",sigle,".xlsx"), overwrite=T)
    
            wb_recap=wb
            
            
            tableau_fiabilisation=cbind(tableau_fiabilisation,tableau_suivi)

            #### Les tabmeaux de fiabilisation en vertical

            fiabilisation=cbind(tableau_suivi[2,],tableau_suivi_stock[2,-1])
            fiabilisation[1,1]=fil

            colnames(fiabilisation)[c(1,2:5)]=c("",seq(1,4))
            colnames(fiabilisation)[c(2,4)]=c("Flux","Stock")

            fiabilisation_fil=rbind(fiabilisation_fil,fiabilisation)
            colnames(fiabilisation_fil)[c(2,4)]=c("Flux","Stock")
            
            if (exists("tableau_fiabilisation")=="TRUE") {
              cat("######################################################################################\n")
              cat("######### Les fichiers des suivi de ",sigle," par agence sont générés avec sucès ######\n")
              cat("######################################################################################\n")
            } else {
              cat("######################################################################################\n")
              cat("######### ERREUR: Les fichiers des suivi de ",sigle," par agence ne sont pas générés ####\n")
              cat("######################################################################################\n")
              
            }
 
       

          #####-----------------------IMPORTATION DES LIBRAIRIES-------------###########
      
      cat("###############################################\n")
      cat("######### FIABILISATION DES DONNEES KYC \n")
      cat("######### ETAPE 2: FIABILISATION PAR AGENT\n")
      cat("##############################################\n")




if (file.exists(paste0(chemin,fil,"//suivi_fiabilisation.txt"))) {
    suivi_fiabilisation=read.csv2(paste0(chemin,fil,"//suivi_fiabilisation.txt"))
      if (colnames(suivi_fiabilisation)[1]=="X"){
      suivi_fiabilisation=suivi_fiabilisation[,-1]
  }
} else {
   suivi_fiabilisation=c()
}


    suivi_fiabilisation=as.data.frame(lapply(suivi_fiabilisation, remove_spaces))



if (file.exists(paste0(chemin,fil,"//suivi_anomalie.txt"))) {
      suivi_anomalie=read.csv2(paste0(chemin,fil,"//suivi_anomalie.txt"), dec=",")
    if (colnames(suivi_anomalie)[1]=="X"){
      suivi_anomalie=suivi_anomalie[,-1]
    }
} else {
   suivi_anomalie=c()
}



    suivi_anomalie=as.data.frame(lapply(suivi_anomalie, remove_spaces))


if (file.exists(paste0(chemin,"//note_groupe.csv"))) {
      note_groupe=read.csv2(paste0(chemin,"//note_groupe.csv"))
    if (colnames(note_groupe)[1]=="X"){
      note_groupe=note_groupe[,-1]
    }
} else {
   note_groupe=c()
}

if (file.exists(paste0(chemin,"//note_groupe_stock.csv"))) {
      note_groupe_stock=read.csv2(paste0(chemin,"//note_groupe_stock.csv"))
    if (colnames(note_groupe_stock)[1]=="X"){
      note_groupe_stock=note_groupe_stock[,-1]
    }
} else {
   note_groupe_stock=c()
}





    
   repertoire=file.path(chemin,fil,"Contrôle de qualité")
   dir.create(repertoire)

   repertoire=file.path(chemin,fil,"Contrôle de qualité","Contrôle qualité Flux")
   dir.create(repertoire)

   repertoire=file.path(chemin,fil,"Contrôle de qualité","Contrôle qualité Stock")
   dir.create(repertoire)

   repertoire=file.path(chemin,fil,"Anomalies par agence")
   dir.create(repertoire)


   tableau_suivi=data.frame(Flux=c("","Taux de fiabilisation","Appréciation"))
   tableau_suivi_stock=data.frame(Stock=c("","Taux de fiabilisation","Appréciation"))
  

    sigle=paste("BOA_",fil, sep="")
 
    wb_cp=createWorkbook()  
    addWorksheet(wb_cp,"Notation CP flux")
    
    writeData(wb_cp,"Notation CP flux", x=cp_flux, startRow=1, startCol=1)
    addStyle(wb_cp,"Notation CP flux",headerStyle, cols=1:ncol(cp_flux), rows=1)


    addWorksheet(wb_cp,"Notation CP stock")
    
    writeData(wb_cp,"Notation CP stock", x=cp_stock, startRow=1, startCol=1)
    addStyle(wb_cp,"Notation CP stock",headerStyle, cols=1:ncol(cp_stock), rows=1)

    saveWorkbook(wb_cp, paste(sep="",paste0(chemin,fil),"//Notation Contrôle Permanent BOA_",fil,".xlsx"), overwrite=T)



     
 
            cat("######### Chargement des données de\n",sigle, "\n")

        # pp_flux/pm_flux déjà en mémoire, pas de relecture des CSV
        pp_ne <- pp_flux
        pp_ne$AGENCE=as.numeric(pp_ne$AGENCE)

        pp_ne=pp_ne[is.na(pp_ne$AGENCE)=="FALSE",]

        pp_ne=select_pp_fields(pp_ne, pp_fields)
        colnames(pp_ne)=toupper(colnames(pp_ne))

        pm_ne <- pm_flux
          pm_ne$AGENCE=as.numeric(pm_ne$AGENCE)

                pm_ne=pm_ne[is.na(pm_ne$AGENCE)=="FALSE",]


        pm_ne=select_pm_fields(pm_ne, pm_fields)

        colnames(pm_ne)=toupper(colnames(pm_ne))
        
        pp_ne$EXPL[is_alphanumeric(pp_ne$EXPL)=="FALSE"]=paste("DIR_AGENCE_",pp_ne$AGENCE[is_alphanumeric(pp_ne$EXPL)=="FALSE"],sep="")
        pm_ne$EXPL[is_alphanumeric(pm_ne$EXPL)=="FALSE"]=paste("DIR_AGENCE_",pm_ne$AGENCE[is_alphanumeric(pm_ne$EXPL)=="FALSE"],sep="")



        pp_ne <- clean_and_mark_anomalies(pp_ne, start_col = 4)
        pm_ne <- clean_and_mark_anomalies(pm_ne, start_col = 4)


        if (exists("pp_ne")=="TRUE" & exists("pm_ne")=="TRUE") {

            cat("######### Les données de\n",sigle, "ont été chargées avec succès \n")

        } else {

            cat("######### Erreur: les données de\n",sigle, "n'ont pas été bien chargées (Voir les formats) #####\n")

        }

pp_ne_f=pp_ne
pm_ne_f=pm_ne

        
        trimestre=100
        Faible=80
        Moyen=100
        Bon=100

        ## Statistique a l'échelle filiale (PP)

     
        a=field_completion_rate(pp_ne, "PAYNAIS", inc)
        b=field_completion_rate(pp_ne, "PROFESSION", inc)
        c=field_completion_rate(pp_ne, "SALAIRE", inc)
        d=field_completion_rate(pp_ne, "CODAPE", inc)
        e=field_completion_rate(pp_ne, "TEL", inc)
        f=field_completion_rate(pp_ne, "ADRESSE", inc)
        g=field_completion_rate(pp_ne, "NUMID", inc)
        h=field_completion_rate(pp_ne, "DATNAIS", inc)
        i=field_completion_rate(pp_ne, "DATVALID", inc)
        j=field_completion_rate(pp_ne, "ORIGINE_REVENU", inc)

        T=length(c(a,b,c,d,e,f,g,h,i,j))
        
       
             
      #           
      #   taux=floor(100*(1-sum(nrow(pp_ne[pp_ne$PAYNAIS=="" | is.na(pp_ne$PAYNAIS)=="TRUE",]),nrow(pp_ne[pp_ne$PROFESSION=="" | is.na(pp_ne$PROFESSION)=="TRUE",]),
      #            nrow(pp_ne[pp_ne$SALAIRE=="" | is.na(pp_ne$SALAIRE)=="TRUE",]), nrow(pp_ne[pp_ne$NUMID=="" | is.na(pp_ne$NUMID)=="TRUE",]),
      #            nrow(pp_ne[pp_ne$CODAPE=="" | is.na(pp_ne$CODAPE)=="TRUE",]),nrow(pp_ne[pp_ne$TEL=="" | is.na(pp_ne$TEL)=="TRUE",]),          
      #            nrow(pp_ne[pp_ne$DATNAIS=="" | is.na(pp_ne$DATNAIS)=="TRUE",]),
      #            nrow(pp_ne[pp_ne$ADRESSE=="" |is.na(pp_ne$ADRESSE)=="TRUE",]),   nrow(pp_ne[pp_ne$NUMID=="" |is.na(pp_ne$NUMID)=="TRUE",]), nrow(pp_ne[pp_ne$DATVALID=="" |is.na(pp_ne$DATVALID)=="TRUE" ,]), 
      #                      nrow(pp_ne[pp_ne$ORIGINE_REV=="" |is.na(pp_ne$ORIGINE_REV)=="TRUE" ,] )
      #            
      #            )/(T*nrow(pp_ne))))
      #  
      #  

      
       
        champs=c("PAYNAIS","PROFESSION","SALAIRE","NUMID","CODAPE","TEL","DATNAIS","ADRESSE","DATVALID","ORIGINE_REVENU")

        taux=compute_taux(pp_ne, champs)
        appreciation=get_appreciation(taux, Faible, Moyen)
        taux=format_percent(taux)

        lieu_naiss=format_percent(a)
        profession=format_percent(b)
        revenu=format_percent(c)
        codape=format_percent(d)
        tel=format_percent(e)
        adresse=format_percent(f)
        nin=format_percent(g)
        datnais=format_percent(h)
        datvalid=format_percent(i)
        origine=format_percent(j)

       
        etat_pp_nes=data.frame(`Lieu de Naissance` = lieu_naiss, Profession = profession,Codape=codape, Revenu = revenu, NIN = nin, TEL=tel, Adresse=adresse,DATNAIS=datnais,DATVALID=datvalid, ORIGINE_REV=origine, `Taux de fiabilisation` =taux, Appréciation=appreciation)##`Taux à rattrapper` = taux_ratt)
        pp=etat_pp_nes[,c(ncol(etat_pp_nes),ncol(etat_pp_nes)-1,ncol(etat_pp_nes)-2)]
        pp_t=data.frame(A="",V="")

        colnames(pp_t)=c(paste(fil),"")
        pp_t[1,]=c("PM","PP")
        pp_t[2,2]=c(pp[1,c(3)])
        pp_t[3,2]=c(pp[1,c(2)])

        rownames(pp_t)=c("","Taux de fiabilisation","Appréciation")
        ## Statistique a l'échelle filiale (PM)

if (nrow(pm_ne)!=0) {


            a=field_completion_rate(pm_ne, "CAPITAL", inc)
            b=field_completion_rate(pm_ne, "CA", inc)
            c=field_completion_rate(pm_ne, "RESULTAT", inc)
            d=field_completion_rate(pm_ne, "RCSNO", inc)
            e=field_completion_rate(pm_ne, "CODAPE", inc)
            f=field_completion_rate(pm_ne, "AGEC", inc)
            g=field_completion_rate(pm_ne, "ORIGINE_REVENU", inc)
            h=field_completion_rate(pm_ne, "TEL", inc)

           
            K=length(c(a,b,c,d,e))

           # taux=floor(100*(1-sum(nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC)=="TRUE",]), nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",]), nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",]),
           #   nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",]), nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),]),
           #   nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),]), nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc | is.na(pm_ne$ORIGINE_REV)=="TRUE",]), nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL)=="TRUE",]))/(K*nrow(pm_ne))))
#
       champs=c("CAPITAL","CA","RESULTAT","RCSNO","CODAPE","AGEC","ORIGINE_REVENU","TEL")

        taux=compute_taux(pm_ne, champs)
        appreciation=get_appreciation(taux, Faible, Moyen)
        taux=format_percent(taux)
        capital=format_percent(a)
        ca=format_percent(b)
        resultat=format_percent(c)
        rcsno=format_percent(d)
        codape=format_percent(e)
        agec=format_percent(f)
        origine=format_percent(g)
        tel=format_percent(h)


            
            etat_pm_nes=data.frame(AGEC=agec,`Capital`=capital, CA = ca, Resultat = resultat, RCSNO = rcsno,CODAPE= codape,  ORIGINE_REV=origine, TEL=tel, `Taux de fiabilisation`=taux, Appréciation=appreciation)##`Taux à rattrapper`=taux_ratt)
            
        pm=etat_pm_nes[,c(ncol(etat_pm_nes),ncol(etat_pm_nes)-1,ncol(etat_pm_nes)-2)]

       pp_t[2,1]=c(pm[1,c(2)])
            pp_t[3,1]=c(pm[1,c(1)])

          } else {
                    pp_t=data.frame(MR=c("PM","N/A","Aucune donnée"),RM=c("PP","N/A","Aucune donnée"))
                    colnames(pp_t)=c(fil,"")
                    rownames(pp_t)=c("","Taux de fiabilisation","Appréciation")
                  }


        tableau_suivi = cbind(tableau_suivi,pp_t)

        tableau_suivi = tableau_suivi[,-1]

   
        

        ## PP
        
        agents=unique(pp_ne$EXPL[grepl("[[:alnum:]]", pp_ne$EXPL)=="TRUE"])
        agents_null_pp=pp_ne[grepl("[[:alnum:]]", pp_ne$EXPL)=="FALSE",]
        exploitant="agent"


        agents_flux_pp=unique(pp_ne$EXPL[grepl("[[:alnum:]]", pp_ne$EXPL)=="TRUE"])
        agents_flux_pm=unique(pm_ne$EXPL[grepl("[[:alnum:]]", pm_ne$EXPL)=="TRUE"])


        etat_expl=data.frame(Agents="",`Nbre clients concernés`="",`Lieu de Naissance`="", Profession ="", Codape="", Revenu = "", NIN="", TEL="",Adresse="",DATNAIS="", DATVALID="", ORIGINE_REV="", `Taux de fiabilisation`="", Appréciation="") # ##, `Taux à rattrapper`=taux_ratt)
        taux_filiale = lapply(agents, taux_function_pp )
        
        taux_filiale_t=bind_results(taux_filiale, etat_expl)
        taux_filiale_t=taux_filiale_t[-which(taux_filiale_t$NIN==""),]
        

        taux_completude_pp = data.frame(Agents=taux_filiale_t$Agents, Taux=taux_filiale_t$Taux.de.fiabilisation, Date=premier_jour_mois_precedent, flux_stock=rep("F", nrow(taux_filiale_t)), pp_pm=rep("P", nrow(taux_filiale_t)))




   



      # minimum = taux_filiale_t[,c(2:8)]
      # minimum_1=c()
      # for (i in 1:ncol (minimum)) {
      #     minimume = gsub("%","",minimum[,i])
      #     minimum_1=cbind(minimum_1, as.numeric(minimume))
      # }
      # minimum_2 = c(paste("BOA", fil),min(minimum_1[,1]),min(minimum_1[,2]),min(minimum_1[,3]),min(minimum_1[,4]),min(minimum_1[,5]),min(minimum_1[,6]),min(minimum_1[,7]))
      # minimum_pp = rbind(minimum_2,minimum_pp)



       cat("###############################################\n")
      cat("######### TRAITEMENT DES ANOMALIES \n")
      cat("##############################################\n")



          stock="n"





anom_pp= function(x) {

          expl=pp_ne[pp_ne$EXPL==x,]
          expl$DATNAIS=dmy(expl$DATNAIS)
          expl$DATOUV=dmy(expl$DATOUV)
          expl$DATVALID=dmy(expl$DATVALID)


          expl$'AGE'=difftime(premier_jour_mois_precedent,expl$DATNAIS,units = "weeks") / 52.143
          expl$AGE=gsub(" week", "", expl$AGE)

          expl$ANOMALIE_AGE=""
          expl$AGE_EER=""

          expl$ANOMALIE_DATE_EER=""

          expl$AGE_CIN=""

          ##########

          expl$AGE_EER=difftime(expl$DATOUV,expl$DATNAIS,units = "weeks") / 52.143

          expl$AGE_EER=gsub(" week", "", expl$AGE_EER)
            expl$AGE_EER=floor(as.numeric( expl$AGE_EER))

          expl$'AGE_CIN'=difftime(premier_jour_mois_precedent,expl$DATVALID,units = "weeks") / 52.143
          expl$AGE_CIN=gsub(" week", "", expl$AGE_CIN)

           expl$AGE_CIN=floor(as.numeric( expl$AGE_CIN))




          mineur_lib <- prerequis$LIB_MINEUR[prerequis$infos==fil]
          if (length(mineur_lib) > 0 && !is.na(mineur_lib) && mineur_lib != "") {
              expl$ANOMALIE_AGE[expl$AGE>=21 & expl$PROFESSION == mineur_lib]="ANOMALIE - Mineur de plus de 21 ans"
          }

          etudiant_lib <- prerequis$LIB_ETUDIANT[prerequis$infos==fil]
          if (length(etudiant_lib) > 0 && !is.na(etudiant_lib) && etudiant_lib != "") {
             expl$ANOMALIE_AGE[expl$AGE>=30 & expl$PROFESSION == etudiant_lib]="ANOMALIE - Etudiant de plus de 30 ans"
          }

          expl$ANOMALIE_DATE_EER[expl$AGE_EER<0]="ANOMALIE - Date EER antérieure à la date de naissance"

           expl$ANOMALIE_CIN[expl$AGE_CIN>0]="ANOMALIE - Document d'identité expiré"
           expl$ANOMALIE_CIN[expl$AGE_CIN<=0]=""


          colnames(anomalies_pp_t)=colnames(expl)

          anomalies_pp_t=rbind(expl,anomalies_pp_t)
  
     }          
   cat("###############################################\n")
      cat("######### DEBUT ANOMALIES PP (1/2) \n")
      cat("##############################################\n")


        anomalies_pp_t=empty_anomalies_pp(pp_ne)
        anomalies_pp=lapply(agents,anom_pp)
        anomalies_pp=do.call("rbind",anomalies_pp)
        if (is.null(anomalies_pp)) {
            anomalies_pp <- empty_anomalies_pp(pp_ne)
        } else {
            anomalies_pp <- anomalies_pp[!is.na(anomalies_pp$CLIENT) & anomalies_pp$CLIENT != "", , drop = FALSE]
        }
        
     cat("###############################################\n")
      cat("######### DEBUT ANOMALIES PP (2/2) \n")
      cat("##############################################\n")
        col_anom_risque=which(names(anomalies_pp) == "RISQUE")
        col_anom_datouv=which(names(anomalies_pp) == "DATOUV")
        anomalies_pp=anomalies_pp[,-c(col_anom_risque,col_anom_datouv)]
        anomalies_pp_t= anomalies_pp %>%
                        filter(if_any(everything(), ~ !is.na(.) & grepl("ANOMALIE", as.character(.), ignore.case = TRUE)))

    agence_flux=unique(anomalies_pp_t$AGENCE)


    function_anom_agent=function(i){

        agence_i=anomalies_pp[anomalies_pp$EXPL==i,]
        agence_i=agence_i[,-c(1:3)]

        agence_i_anomalies=as.matrix(agence_i)
        n_anorm_i= sum(grepl("ANOMALIE",agence_i_anomalies, ignore.case=T))

        l=ncol(agence_i)-6
        agence_i=agence_i[,c(1:l)]
        total=ncol(agence_i)*nrow(agence_i) - length(which(agence_i==""))
        taux_ano_i=floor(100*(1-n_anorm_i/total))
        taux_anomalie_i=paste(taux_ano_i,"%",sep="")
        anomalie_agent_i=c(i,taux_anomalie_i)
        anomalie_agent=rbind(anomalie_agent,anomalie_agent_i)
        }

        anomalie_agent=data.frame(AGENT="",TAUX_NON_ANOMALIE="")
        wb_anom_agents=createWorkbook()
        addWorksheet(wb_anom_agents,paste("Tx non anomalie BOA_",fil))
        addWorksheet(wb_anom_agents,paste("Tx non anomalie agences_flux"))
        addWorksheet(wb_anom_agents,paste("Tx non anomalie agences_stock"))
        addWorksheet(wb_anom_agents,paste("Tx non anomalie agents_flux"))
        addWorksheet(wb_anom_agents,paste("Tx non anomalie agents_stock"))


        taux_agences=matrix(,ncol=2)
        for(x in unique(pp_ne$AGENCE)) {
          

                    anomalie_agent=data.frame(AGENT="",TAUX_NON_ANOMALIE="")
                    agence=anomalies_pp_t[anomalies_pp_t$AGENCE==x,]
                    if (nrow(agence!=0)) {


                        ### Anomalies par agents et par agence


                        agents_anom=unique(agence$EXPL)

                        anomalie_agent_t=lapply(agents_anom,function_anom_agent)

                        anomalie_agent=do.call("rbind",anomalie_agent_t)

                        anomalie_agent=anomalie_agent[!anomalie_agent$AGENT=="",]



                        writeData(wb_anom_agents,paste("Tx non anomalie agents_flux"), x=anomalie_agent, startRow=1, startCol=1)
                        addStyle(wb_anom_agents,paste("Tx non anomalie agents_flux"), headerStyle, cols=1:ncol(anomalie_agent), rows=1)

                     
                  
                        expl=anomalies_pp[anomalies_pp$AGENCE==x,]

                        expl=expl[,-c(1:3)]

                        expl_anomalies=as.matrix(expl)
                        n_anorm_i= sum(grepl("ANOMALIE",expl_anomalies, ignore.case=T))

                        l=ncol(expl)-6
                        expl=expl[,c(1:l)]

                        total=ncol(expl)*nrow(expl) - length(which(expl==""))
                        taux_anomalie=floor(100*(1-n_anorm_i/total))

                                
                        taux_anomalie=paste(taux_anomalie,"%",sep="")

                         t1=c(paste("Agence",x, sep=" "),"Pourcentage")
                         t2=c("Taux de non anomalie", taux_anomalie)

                         taux_anomalie_t=as.data.frame(rbind(t1,t2))
                         colnames(taux_anomalie_t)=taux_anomalie_t[1,]
                         taux_anomalie_t=taux_anomalie_t[-1,]
                         
                     
                         taux_agences_i=c(paste0("Agence ",x),taux_anomalie)

                         taux_agences=rbind(taux_agences,taux_agences_i)
                         
                        taux_agences=as.data.frame(taux_agences)
                        colnames(taux_agences)=c("Agences","Taux de non anomalies_Flux")

                          ###### Taux Anomalie par agent

                        wb_agence=createWorkbook()
                        wb_anom_agence=createWorkbook()
                        wb_anom_agence_s=createWorkbook()

                  


                        colnames(taux_anomalie_t)[1]= paste("FLUX AGENCE",x)
                        colnames(anomalie_agent)[2]="TAUX_NON_ANOMALIE"
                        sheet_non_anom <- unique_sheet_name(wb_anom_agence, paste0(x,"_Taux de non anomalie"))
                        sheet_anom_flux <- unique_sheet_name(wb_agence, paste0(x,"_Anomalies flux"))
                        addWorksheet(wb_anom_agence, sheet_non_anom)
                        # addWorksheet(wb_agence,paste0("RECAP AGENTS"))
                        addWorksheet(wb_agence, sheet_anom_flux)



                        writeData(wb_agence, sheet_anom_flux, x=agence, startRow=1, startCol=1)
                        addStyle(wb_agence, sheet_anom_flux, headerStyle, cols=1:ncol(agence), rows=1)

                        writeData(wb_anom_agence, sheet_non_anom, x=taux_anomalie_t, startRow=1, startCol=1)

                        writeData(wb_anom_agence, sheet_non_anom, x=anomalie_agent, startRow=1, startCol=5)
                        
                            saveWorkbook(wb_anom_agence, paste(sep="",paste(chemin,fil,"//Anomalies par agence//",sep=""),"Agence_",paste(x)," flux.xlsx"), overwrite=T)

                            saveWorkbook(wb_agence, paste(sep="",paste(chemin,fil,"//Contrôle de qualité//Contrôle qualité Flux//",sep=""),"Agence_",paste(x),".xlsx"), overwrite=T)
                          
                       }

                     
                       
                  }

             taux_agences=taux_agences[-1,]
             writeData(wb_anom_agents,paste("Tx non anomalie agences_flux"), x=taux_agences, startRow=1, startCol=1)
             addStyle(wb_anom_agents,paste("Tx non anomalie agences_flux"), headerStyle, cols=1:ncol(taux_agences), rows=1)


      
          #aux_agences=matrix(,ncol=2)
          #gents=unique(pp_ne$AGENCE)#("[[:alnum:]]", pp_ne$EXPL)=="TRUE"])
          #apply(agents,anomalie_agence)
        
                     
    agents_anom=unique(anomalies_pp_t$EXPL)
    agents_anom=agents_anom[!is.na(agents_anom) & agents_anom!=""]
    anomalie_agent=data.frame(AGENT="",TAUX_NON_ANOMALIE="")
    anomalie_agent_t=lapply(agents_anom,function_anom_agent)
    anomalie_agent=do.call("rbind",anomalie_agent_t)
    anomalie_agent=reset_row_names(anomalie_agent)
    anomalie_agent=anomalie_agent[!anomalie_agent$AGENT=="",]
    anomalie_agent=reset_row_names(anomalie_agent)

       cat("###############################################\n")
      cat("######### FIN ANOMALIES PP \n")
      cat("##############################################\n")

    if (is.null(anomalie_agent)=="FALSE") {
         colnames(anomalie_agent)[1]="Agents"
         wb_agence_anomalie_flux=createWorkbook()
         addWorksheet(wb_agence_anomalie_flux,"Appréciation")
         writeData(wb_agence_anomalie_flux,"Appréciation", x=anomalie_agent, startRow=1, startCol=1)
         addStyle(wb_agence_anomalie_flux,"Appréciation",headerStyle, cols=1:ncol(anomalie_agent), rows=1)
         saveWorkbook(wb_agence_anomalie_flux, paste(sep="",paste(chemin,fil,"//Contrôle de qualité//Contrôle qualité Flux//",sep=""),"Contrôle de non-anomalie par agent_Flux",".xlsx"), overwrite=T)
    
       writeData(wb_anom_agents,paste("Tx non anomalie agents_flux"), x=anomalie_agent, startRow=1, startCol=1)
       addStyle(wb_anom_agents,paste("Tx non anomalie agents_flux"), headerStyle, cols=1:ncol(anomalie_agent), rows=1)

    } else {
       anomalie_agent
    }
  
  
   ## Taux non anomalie des agents flux


           cat("###############################################\n")
           cat("#########Début du taux d'agence 1\n")
           cat("##############################################\n")


        if (nrow(anomalies_pp)!=0) {
            anomalies_pp=reset_row_names(anomalies_pp)
            expl=reset_row_names(anomalies_pp)

            expl=expl[,-c(1:3)]
            expl=reset_row_names(expl)
            expl_anomalies=as.matrix(expl)
            n_anorm_i= sum(grepl("ANOMALIE",expl_anomalies, ignore.case=T))
            l=ncol(expl)-6
            expl=expl[,c(1:l)]
            expl=reset_row_names(expl)
            total=ncol(expl)*nrow(expl) - length(which(expl==""))
            taux_anomalie=floor(100*(1-n_anorm_i/total))      
            taux_anomalie=unname(paste(taux_anomalie,"%",sep=""))
            taux_anomalie_fil=data.frame(FLUX="",TAUX_NON_ANOMALIE=taux_anomalie, stringsAsFactors=FALSE)
            taux_anomalie_fil_flux=reset_row_names(taux_anomalie_fil)            

        writeData(wb_anom_agents,paste("Tx non anomalie BOA_",fil), x=taux_anomalie_fil_flux, startRow=1, startCol=1)
        addStyle(wb_anom_agents,paste("Tx non anomalie BOA_",fil), headerStyle, cols=1:ncol(taux_anomalie_fil_flux), rows=1)
         
        }
                   cat("###############################################\n")
           cat("#########Début du taux d'agence 2 \n")
           cat("##############################################\n")
                  
           ## PM
        exploitant="agent"
        agents_pm=unique(pm_ne$EXPL[grepl("[[:alnum:]]", pm_ne$EXPL)=="TRUE"])
        agents_null_pm=pm_ne[grepl("[[:alnum:]]", pm_ne$EXPL)=="FALSE",]

        etat_expl=data.frame(Agents="",`Nbre clients concernés`="", AGEC="", Capital="", CA = "", Resultat = "", RCSNO = "",CODAPE= "", ORIGINE_REV="", TEL="", `Taux de fiabilisation`="", Appréciation="" )##`Taux à rattrapper`="")
        taux_filiale_pm = lapply(agents_pm,taux_function_pm)
        
        taux_filiale_pm=bind_results(taux_filiale_pm, etat_expl)
        taux_filiale_pm=taux_filiale_pm[-which(taux_filiale_pm$RCSNO==""),]


        taux_completude_pm = data.frame(Agents=taux_filiale_pm$Agents, Taux=taux_filiale_pm$Taux.de.fiabilisation, Date=premier_jour_mois_precedent, flux_stock=rep("F", nrow(taux_filiale_pm)), pp_pm=rep("M", nrow(taux_filiale_pm)))


          #### les taux d'appréciation


          cat("###############################################\n")
           cat("#########Début du taux d'agence 3 \n")
           cat("##############################################\n")


        #### les taux d'appréciation PM et PP combinés min(Txp,Txm)

        app_flux <- compute_app_flux(taux_filiale_t, taux_filiale_pm)
        app_flux <- app_flux[!(is.na(app_flux$Agents) | app_flux$Agents==""),]

        
         if ((is.null(str(anomalie_agent$AGENT))=="TRUE")) {
          anomalie_agent=data.frame(Agents=anomalies_pp$EXPL, TAUX_NON_ANOMALIE=rep("100%",length(anomalies_pp$EXPL)))

      }


        taux_app_flux=app_flux

        wb_anomalies_fliale=createWorkbook()
       
       
        taux_app_flux=left_join(taux_app_flux,anomalie_agent,by="Agents")

        taux_app_flux=taux_app_flux[,-4]

        taux_app_flux=left_join(taux_app_flux,cp_flux,by="Agents")

        taux_app_flux$TAUX_NON_ANOMALIE=as.numeric(gsub("%","",taux_app_flux$TAUX_NON_ANOMALIE))

        taux_app_flux$Note_1=""

        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE<=80 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Très bien"]="Insatisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE<=80 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Bien"]="Insatisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE<=80 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Moyen"]="Insatisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE<=80 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Passable"]="Insatisfaisant"


        taux_app_flux$Note_1[(taux_app_flux$TAUX_NON_ANOMALIE<100 & taux_app_flux$TAUX_NON_ANOMALIE>80) & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Très bien"]="Satisfaisant"
        taux_app_flux$Note_1[(taux_app_flux$TAUX_NON_ANOMALIE<100 & taux_app_flux$TAUX_NON_ANOMALIE>80) & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Bien"]="Satisfaisant"
        taux_app_flux$Note_1[(taux_app_flux$TAUX_NON_ANOMALIE<100 & taux_app_flux$TAUX_NON_ANOMALIE>80) & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Moyen"]="Insatisfaisant"
        taux_app_flux$Note_1[(taux_app_flux$TAUX_NON_ANOMALIE<100 & taux_app_flux$TAUX_NON_ANOMALIE>80) & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Passable"]="Insatisfaisant"

        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE==100 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Très bien"]="Très satisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE==100 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Bien"]="Satisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE==100 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Moyen"]="Satisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE==100 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Passable"]="Insatisfaisant"


        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE<=80 & (is.na(taux_app_flux$NOTE_CONTROLE_PERMANANT)=="TRUE" | taux_app_flux$NOTE_CONTROLE_PERMANANT=="")]="Insatisfaisant"

        taux_app_flux$Note_1[(taux_app_flux$TAUX_NON_ANOMALIE < 100 & taux_app_flux$TAUX_NON_ANOMALIE > 80) & (is.na(taux_app_flux$NOTE_CONTROLE_PERMANANT)=="TRUE" | taux_app_flux$NOTE_CONTROLE_PERMANANT=="") ]="Satisfaisant"

        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE==100 & (is.na(taux_app_flux$NOTE_CONTROLE_PERMANANT)=="TRUE" | taux_app_flux$NOTE_CONTROLE_PERMANANT=="")]="Très satisfaisant"


        note_cp=data.frame(NOTE_CONTROLE_PERMANANT=taux_app_flux$NOTE_CONTROLE_PERMANANT)
        note_cp$NOTE_CONTROLE_PERMANANT[is.na(note_cp$NOTE_CONTROLE_PERMANANT)]=0

        note_cp[note_cp$NOTE_CONTROLE_PERMANANT=="Très bien"]=4
        note_cp[note_cp$NOTE_CONTROLE_PERMANANT=="Bien"]=3
        note_cp[note_cp$NOTE_CONTROLE_PERMANANT=="Moyen"]=2
        note_cp[note_cp$NOTE_CONTROLE_PERMANANT=="Passable"]=1

        note_filiale_fll=mean((note_cp$NOTE_CONTROLE_PERMANANT), na.rm=FALSE)

        note_finale=data.frame(Filiale=fil, Notation=note_filiale_fll, Date=ymd(premier_jour_mois_precedent))
        note_groupe=rbind(note_finale,note_groupe)

        write.csv2(note_groupe,paste0(chemin,"note_groupe.csv"))

       ## Note Finale

         if (trimestre_actuel=="1") {

          taux_app_flux$Appreciation_Globale=""

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=5 & taux_app_flux$Note_1=="Très satisfaisant"]="Faible++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=5 & taux_app_flux$Note_1=="Satisfaisant"]="Faible+"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=5 & taux_app_flux$Note_1=="Insatisfaisant"]="Faible-"

          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>5 & taux_app_flux$Taux_Completude <=30) & taux_app_flux$Note_1=="Très satisfaisant"]="Moyen++"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>5 & taux_app_flux$Taux_Completude <=30) & taux_app_flux$Note_1=="Satisfaisant"]="Moyen+"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>5 & taux_app_flux$Taux_Completude <=30) & taux_app_flux$Note_1=="Insatisfaisant"]="Moyen-"

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>30 & taux_app_flux$Note_1=="Très satisfaisant"]="Bon++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>30 & taux_app_flux$Note_1=="Satisfaisant"]="Bon+"
           taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>30 & taux_app_flux$Note_1=="Insatisfaisant"]="Bon-"
         }

           if (trimestre_actuel=="2") {

          taux_app_flux$Appreciation_Globale=""

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=30 & taux_app_flux$Note_1=="Très satisfaisant"]="Faible++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=30 & taux_app_flux$Note_1=="Satisfaisant"]="Faible+"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=30 & taux_app_flux$Note_1=="Insatisfaisant"]="Faible-"

          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>30 & taux_app_flux$Taux_Completude <=60) & taux_app_flux$Note_1=="Très satisfaisant"]="Moyen++"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>30 & taux_app_flux$Taux_Completude <=60) & taux_app_flux$Note_1=="Satisfaisant"]="Moyen+"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>30 & taux_app_flux$Taux_Completude <=60) & taux_app_flux$Note_1=="Insatisfaisant"]="Moyen-"

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>60 & taux_app_flux$Note_1=="Très satisfaisant"]="Bon++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>60 & taux_app_flux$Note_1=="Satisfaisant"]="Bon+"
           taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>60 & taux_app_flux$Note_1=="Insatisfaisant"]="Bon-"
         }

           if (trimestre_actuel=="3") {

          taux_app_flux$Appreciation_Globale=""

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=60 & taux_app_flux$Note_1=="Très satisfaisant"]="Faible++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=60 & taux_app_flux$Note_1=="Satisfaisant"]="Faible+"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=60 & taux_app_flux$Note_1=="Insatisfaisant"]="Faible-"

          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>60 & taux_app_flux$Taux_Completude <=90) & taux_app_flux$Note_1=="Très satisfaisant"]="Moyen++"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>60 & taux_app_flux$Taux_Completude <=90) & taux_app_flux$Note_1=="Satisfaisant"]="Moyen+"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>60 & taux_app_flux$Taux_Completude <=90) & taux_app_flux$Note_1=="Insatisfaisant"]="Moyen-"

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>90 & taux_app_flux$Note_1=="Très satisfaisant"]="Bon++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>90 & taux_app_flux$Note_1=="Satisfaisant"]="Bon+"
           taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>90 & taux_app_flux$Note_1=="Insatisfaisant"]="Bon-"
         }

           if (trimestre_actuel=="4") {

          taux_app_flux$Appreciation_Globale=""

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=65 & taux_app_flux$Note_1=="Très satisfaisant"]="Faible++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=65 & taux_app_flux$Note_1=="Satisfaisant"]="Faible+"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=65 & taux_app_flux$Note_1=="Insatisfaisant"]="Faible-"

          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>55 & taux_app_flux$Taux_Completude <=95) & taux_app_flux$Note_1=="Très satisfaisant"]="Moyen++"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>65 & taux_app_flux$Taux_Completude <=95) & taux_app_flux$Note_1=="Satisfaisant"]="Moyen+"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>65 & taux_app_flux$Taux_Completude <=95) & taux_app_flux$Note_1=="Insatisfaisant"]="Moyen-"

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>95 & taux_app_flux$Note_1=="Très satisfaisant"]="Bon++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>95 & taux_app_flux$Note_1=="Satisfaisant"]="Bon+"
           taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>95 & taux_app_flux$Note_1=="Insatisfaisant"]="Bon-"
         }


        taux_app_flux=taux_app_flux[,-5]
        taux_app_flux$Taux_Completude=paste(taux_app_flux$Taux_Completude,"%")
        taux_app_flux$TAUX_NON_ANOMALIE=paste(taux_app_flux$TAUX_NON_ANOMALIE,"%")

         taux_app_flux$Mesure=""

         taux_app_flux$Mesure[taux_app_flux$Appreciation_Globale=="Faible++" | taux_app_flux$Appreciation_Globale=="Faible+" | taux_app_flux$Appreciation_Globale=="Moyen++" 
                                          |taux_app_flux$Appreciation_Globale=="Faible+"]="Demande d’explication et décote sur le bonus si motif infondé"

        taux_app_flux$Mesure[taux_app_flux$Appreciation_Globale=="Faible-" | taux_app_flux$Appreciation_Globale=="Moyen-" | taux_app_flux$Appreciation_Globale=="Bon-"] = "Demande d’explication avec sanction forte et décote sur le bonus si motif infondé"

        taux_app_flux$Mesure[taux_app_flux$Appreciation_Globale=="Bon++" | taux_app_flux$Appreciation_Globale=="Bon+"] = "Impact positif sur le bonus"

        taux_app_flux=taux_app_flux[taux_app_flux$Mesure!="",]

        colnames(taux_app_flux)=c("Agents","Taux de complétude","Taux de non-anomalie","Note Contrôle Permanent","Appréciation Globale","Mesures de sanctions")
              
         wb_note_flux=createWorkbook()
         addWorksheet(wb_note_flux,"Appréciation")
         writeData(wb_note_flux,"Appréciation", x=taux_app_flux, startRow=1, startCol=1)
         addStyle(wb_note_flux,"Appréciation",headerStyle, cols=1:ncol(taux_app_flux), rows=1)  
         saveWorkbook(wb_note_flux, paste(sep="",paste(chemin,fil,"//Contrôle de qualité//Contrôle qualité Flux//",sep=""),"Notation des agents_Flux",".xlsx"), overwrite=T)
               
               
       addWorksheet(wb_anomalies_fliale,"Appréciation agents_flux")
                        writeData(wb_anomalies_fliale,"Appréciation agents_flux", x=taux_app_flux, startRow=1, startCol=1)
                               addStyle(wb_anomalies_fliale,"Appréciation agents_flux",headerStyle, cols=1:ncol(taux_app_flux), rows=1)


 
   

 
     rm(taux_app_flux)

  
     
      cat("###############################################\n")
      cat("######### Fin traitement flux  \n")
      cat("##############################################\n")
        
     
        rm(pp_ne,pm_ne)


        ### LE stock

          cat("######### Chargement des données Stock de\n",sigle, "\n")
        # Importatations des donnees
     
          # pp_stock/pm_stock déjà en mémoire, pas de relecture des CSV _STOCK
          pp_ne <- pp_stock
            pp_ne$AGENCE=as.numeric(pp_ne$AGENCE)

          #
          pp_ne=select_pp_fields(pp_ne, pp_fields)
          colnames(pp_ne)=toupper(colnames(pp_ne))


          pm_ne <- pm_stock
            pm_ne$AGENCE=as.numeric(pm_ne$AGENCE)

          #
          pm_ne=select_pm_fields(pm_ne, pm_fields)
          colnames(pm_ne)=toupper(colnames(pm_ne))
  
          pp_ne$EXPL[is_alphanumeric(pp_ne$EXPL)=="FALSE"]=paste("DIR_AGENCE_",pp_ne$AGENCE[is_alphanumeric(pp_ne$EXPL)=="FALSE"],sep="")
          pm_ne$EXPL[is_alphanumeric(pm_ne$EXPL)=="FALSE"]=paste("DIR_AGENCE_",pm_ne$AGENCE[is_alphanumeric(pm_ne$EXPL)=="FALSE"],sep="")


          pp_ne <- clean_and_mark_anomalies(pp_ne, start_col = 4)
          pm_ne <- clean_and_mark_anomalies(pm_ne, start_col = 4)


          if (exists("pp_ne")=="TRUE" & exists("pm_ne")=="TRUE") {

              cat("######### Les données Stock de\n",sigle, "ont été chargées avec succès \n")

          } else {

              cat("######### Erreur: les données Stock de\n",sigle, "n'ont pas été bien chargées (Voir les formats) #####\n")

          }

        pp_ne_s=pp_ne
        pm_ne_s=pm_ne


      cat("###############################################\n")
      cat("######### Début traitement stock  \n")
      cat("##############################################\n")
        
        
        ##-----Appréciation du Stock-####
        
        if (trimestre_actuel=="1"){
          trimestre=30
          Faible=5
          Moyen=30
          
        } else if (trimestre_actuel=="2") {
          trimestre=60
          Faible=30
          Moyen=60
        }  else if (trimestre_actuel=="3") {
          trimestre=90
          Faible=60
          Moyen=90
        }  else {
          trimestre=95
          Faible=65
          Moyen=95
        }
              

        ## Statistique a l'échelle filiale (PP)
        a=field_completion_rate(pp_ne, "PAYNAIS", inc)
        b=field_completion_rate(pp_ne, "PROFESSION", inc)
        c=field_completion_rate(pp_ne, "SALAIRE", inc)
        d=field_completion_rate(pp_ne, "CODAPE", inc)
        e=field_completion_rate(pp_ne, "TEL", inc)
        f=field_completion_rate(pp_ne, "ADRESSE", inc)
        g=field_completion_rate(pp_ne, "NUMID", inc)
        h=field_completion_rate(pp_ne, "DATNAIS", inc)
        i=field_completion_rate(pp_ne, "DATVALID", inc)
        j=field_completion_rate(pp_ne, "ORIGINE_REVENU", inc)

        T=length(c(a,b,c,d,e,f,g,h,i,j))
        
       
                      
      #  taux=floor(100*(1-sum(nrow(pp_ne[pp_ne$PAYNAIS=="" | is.na(pp_ne$PAYNAIS)=="TRUE",]),nrow(pp_ne[pp_ne$PROFESSION=="" | is.na(pp_ne$PROFESSION)=="TRUE",]),
      #           nrow(pp_ne[pp_ne$SALAIRE=="" | is.na(pp_ne$SALAIRE)=="TRUE",]), nrow(pp_ne[pp_ne$NUMID=="" | is.na(pp_ne$NUMID)=="TRUE",]),
      #           nrow(pp_ne[pp_ne$CODAPE=="" | is.na(pp_ne$CODAPE)=="TRUE",]),nrow(pp_ne[pp_ne$TEL=="" | is.na(pp_ne$TEL)=="TRUE",]),          
      #           nrow(pp_ne[pp_ne$DATNAIS=="" | is.na(pp_ne$DATNAIS)=="TRUE",]),
      #           nrow(pp_ne[pp_ne$ADRESSE=="" |is.na(pp_ne$ADRESSE)=="TRUE",]),   nrow(pp_ne[pp_ne$NUMID=="" |is.na(pp_ne$NUMID)=="TRUE",]), nrow(pp_ne[pp_ne$DATVALID=="" |is.na(pp_ne$DATVALID)=="TRUE" ,]), 
      #                     nrow(pp_ne[pp_ne$ORIGINE_REV=="" |is.na(pp_ne$ORIGINE_REV)=="TRUE" ,])
      #           
      #           )/(T*nrow(pp_ne))))
      # 
      
       
        champs=c("PAYNAIS","PROFESSION","SALAIRE","NUMID","CODAPE","TEL","DATNAIS","ADRESSE","DATVALID","ORIGINE_REVENU")

        taux=compute_taux(pp_ne, champs)
        appreciation=get_appreciation(taux, Faible, Moyen)
        taux=format_percent(taux)

        lieu_naiss=format_percent(a)
        profession=format_percent(b)
        revenu=format_percent(c)
        codape=format_percent(d)
        tel=format_percent(e)
        adresse=format_percent(f)
        nin=format_percent(g)
        datnais=format_percent(h)
        datvalid=format_percent(i)
        origine=format_percent(j)



       
        etat_pp_nes=data.frame(`Lieu de Naissance` = lieu_naiss, Profession = profession,Codape=codape, Revenu = revenu, NIN = nin, TEL=tel, Adresse=adresse,DATNAIS=datnais,DATVALID=datvalid, ORIGINE_REV=origine, `Taux de fiabilisation` =taux, Appréciation=appreciation)##`Taux à rattrapper` = taux_ratt)
        pp=etat_pp_nes[,c(ncol(etat_pp_nes),ncol(etat_pp_nes)-1,ncol(etat_pp_nes)-2)]
        pp_t=data.frame(A="",V="")

        colnames(pp_t)=c(paste(fil),"")
        pp_t[1,]=c("PM","PP")
        pp_t[2,2]=c(pp[1,c(3)])
        pp_t[3,2]=c(pp[1,c(2)])

        rownames(pp_t)=c("","Taux de fiabilisation","Appréciation")

        

        ## Statistique a l'échelle filiale (PM)
            a=field_completion_rate(pm_ne, "CAPITAL", inc)
            b=field_completion_rate(pm_ne, "CA", inc)
            c=field_completion_rate(pm_ne, "RESULTAT", inc)
            d=field_completion_rate(pm_ne, "RCSNO", inc)
            e=field_completion_rate(pm_ne, "CODAPE", inc)
            f=field_completion_rate(pm_ne, "AGEC", inc)
            g=field_completion_rate(pm_ne, "ORIGINE_REVENU", inc)
            h=field_completion_rate(pm_ne, "TEL", inc)

           
            K=length(c(a,b,c,d,e))

           #taux=floor(100*(1-sum(nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC)=="TRUE",]), nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",]), nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",]),
           #  nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",]), nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),]),
           #  nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),]), nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc | is.na(pm_ne$ORIGINE_REV)=="TRUE",]), nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL)=="TRUE",]))/(K*nrow(pm_ne))))

                   champs=c("CAPITAL","CA","RESULTAT","RCSNO","CODAPE","AGEC","ORIGINE_REVENU","TEL")

        taux=compute_taux(pm_ne, champs)
        appreciation=get_appreciation(taux, Faible, Moyen)
        taux=format_percent(taux)
        capital=format_percent(a)
        ca=format_percent(b)
        resultat=format_percent(c)
        rcsno=format_percent(d)
        codape=format_percent(e)
        agec=format_percent(f)
        origine=format_percent(g)
        tel=format_percent(h)
            
            etat_pm_nes=data.frame(AGEC=agec,`Capital`=capital, CA = ca, Resultat = resultat, RCSNO = rcsno,CODAPE= codape,  ORIGINE_REV=origine, TEL=tel, `Taux de fiabilisation`=taux, Appréciation=appreciation)##`Taux à rattrapper`=taux_ratt)
            
        pm=etat_pm_nes[,c(ncol(etat_pm_nes),ncol(etat_pm_nes)-1,ncol(etat_pm_nes)-2)]
        
       

        pp_t[2,1]=c(pm[1,c(2)])
        pp_t[3,1]=c(pm[1,c(1)])
     
        tableau_suivi_stock = cbind(tableau_suivi_stock,pp_t)
        tableau_suivi_stock = tableau_suivi_stock[,-1]    

        ## PP

        stock="y"
        exploitant="agent"
        agents=unique(pp_ne$EXPL[grepl("[[:alnum:]]", pp_ne$EXPL)=="TRUE"])
        agents_null_pp=pp_ne[grepl("[[:alnum:]]", pp_ne$EXPL)=="FALSE",]
        
        agents_stock_pp=unique(pp_ne$EXPL[grepl("[[:alnum:]]", pp_ne$EXPL)=="TRUE"])
        agents_stock_pm=unique(pm_ne$EXPL[grepl("[[:alnum:]]", pm_ne$EXPL)=="TRUE"])

        
        etat_expl=data.frame(Agents="",`Nbre clients concernés`="",`Lieu de Naissance`="", Profession ="", Codape="", Revenu = "", NIN="", TEL="",Adresse="",DATNAIS="", DATVALID="", ORIGINE_REV="", `Taux de fiabilisation`="", Appréciation="") # ##, `Taux à rattrapper`=taux_ratt)
        taux_filiale = lapply(agents,taux_function_pp)

        taux_filiale_t_stock=bind_results(taux_filiale, etat_expl)
        taux_filiale_t_stock=taux_filiale_t_stock[-which(taux_filiale_t_stock$NIN==""),]

        taux_completude_stock_pp = data.frame(Agents=taux_filiale_t_stock$Agents, Taux=taux_filiale_t_stock$Taux.de.fiabilisation, Date=rep(premier_jour_mois_precedent,nrow(taux_filiale_t_stock)), flux_stock=rep("S", nrow(taux_filiale_t_stock)), pp_pm=rep("P", nrow(taux_filiale_t_stock)))


        ########## Anomalies par agent
               
        anomalies_pp_t=empty_anomalies_pp(pp_ne)
        anomalies_pp=lapply(agents,anom_pp)

        anomalies_pp=do.call("rbind",anomalies_pp)
        if (is.null(anomalies_pp)) {
            anomalies_pp <- empty_anomalies_pp(pp_ne)
        } else {
            anomalies_pp <- anomalies_pp[!is.na(anomalies_pp$CLIENT) & anomalies_pp$CLIENT != "", , drop = FALSE]
        }


      # Les agents avec les clients en anomalie
        anomalies_pp_t= anomalies_pp %>%
                        filter(if_any(everything(), ~ !is.na(.) & grepl("ANOMALIE", as.character(.), fixed = TRUE)))

        les_anomalies=data.frame(AGENCE=anomalies_pp_t$AGENCE, EXPL=anomalies_pp_t$EXPL, CLIENT=anomalies_pp_t$CLIENT, CODAPE=anomalies_pp_t$CODAPE, 
                                 IDP=anomalies_pp_t$IDP, ANOMALIE_AGE=anomalies_pp_t$ANOMALIE_AGE, ANOMALIE_DATE_EER=anomalies_pp_t$ANOMALIE_DATE_EER, ANOMALIE_CIN=anomalies_pp_t$ANOMALIE_CIN)

        idx_ppe <- match(les_anomalies$CLIENT, ppe_stock$CLIENT)
        les_anomalies$AGENCELIB <- ppe_stock$AGENCELIB[idx_ppe]
        les_anomalies$PPE <- ppe_stock$PPE[idx_ppe]

        if ("AGENCE" %in% names(les_anomalies)) {
            les_anomalies$AGENCE <- pad_agence5(les_anomalies$AGENCE)
        }
        

    les_anomalies$AGENCE <- sprintf("%05d", as.integer(les_anomalies$AGENCE))
    a=which(colnames(les_anomalies)=="AGENCELIB")

    les_anomalies=les_anomalies[,-a]
    les_anomalies[les_anomalies=="NA"]=""
    les_anomalies[is.na(les_anomalies)]=""


    les_anomalies= les_anomalies[les_anomalies$ANOMALIE_AGE != "" | les_anomalies$ANOMALIE_DATE_EER != "" | les_anomalies$ANOMALIE_CIN != "" , ]
   
    agences_pm= unique(data.frame(AGENCE=pm_stock$AGENCE, AGENCELIB=pm_stock$AGENCELIB))
    agences_pm$AGENCE <- sprintf("%05d", as.integer(agences_pm$AGENCE))

    
    agences_pp= unique(data.frame(AGENCE=pp_stock$AGENCE, AGENCELIB=pp_stock$AGENCELIB))
    agences_pp$AGENCE <- sprintf("%05d", as.integer(agences_pp$AGENCE))

    agences= unique(rbind(agences_pm, agences_pp))

    les_anomalies_final = left_join(les_anomalies, agences, by = "AGENCE") 
    write.csv2(les_anomalies_final, paste(sep="",chemin,fil,"//data//anomalies_",fil,".csv"), row.names = FALSE,  quote = TRUE)

        #anomalies_pp_t=data.frame(AGENCE=anomalies_pp$AGENCE, EXPL=anomalies_pp$EXPL, CLIENT=anomalies_pp$CLIENT, DATNAIS=anomalies_pp$DATNAIS,DATE_EER=anomalies_pp$DATOUV,PROFESSION=anomalies_pp$PROFESSION,AGE=anomalies_pp$AGE,
         #                 ANOMALIE_AGE=anomalies_pp$ANOMALIE_AGE,AGE_EER=anomalies_pp$AGE_EER,ANOMALIE_DATE_EER=anomalies_pp$ANOMALIE_DATE_EER,DATVALID_CIN=anomalies_pp$DATVALID,ANOMALIE_CIN=anomalies_pp$ANOMALIE_CIN)

        agence_stock=unique(anomalies_pp_t$AGENCE)


        agents_anom=unique(anomalies_pp_t$EXPL)
        agents_anom=agents_anom[!is.na(agents_anom) & agents_anom!=""]
        anomalie_agent=data.frame(AGENT="",TAUX_NON_ANOMALIE="")

        anomalie_agent_t=lapply(agents_anom,function_anom_agent)

        anomalie_agent=do.call("rbind",anomalie_agent_t)
        anomalie_agent=reset_row_names(anomalie_agent)

        anomalie_agent=anomalie_agent[!anomalie_agent$AGENT=="",]
        anomalie_agent=reset_row_names(anomalie_agent)

        wb_agence_anomalie_stock=createWorkbook()
        addWorksheet(wb_agence_anomalie_stock,"Appréciation")
        writeData(wb_agence_anomalie_stock,"Appréciation", x=anomalie_agent, startRow=1, startCol=1)    

        addStyle(wb_agence_anomalie_stock,"Appréciation",headerStyle, cols=1:ncol(anomalie_agent), rows=1)
        saveWorkbook(wb_agence_anomalie_stock, paste(sep="",paste(chemin,fil,"//Contrôle de qualité//Contrôle qualité Stock//",sep=""),"Contrôle de non-anomalie par agent_Stock",".xlsx"), overwrite=T)
  
        ## Taux non anomalie des agents stock
        
        agent_s=unique(pp_ne$EXPL)

        diff_agent=setdiff(agent_s, anomalie_agent$AGENT)

        if (length(diff_agent)!=0) {

          diff_agent_tab= data.frame(AGENT=diff_agent,TAUX_NON_ANOMALIE=rep("100%",length(diff_agent)))
            anomalie_agent=rbind(anomalie_agent,diff_agent_tab)
        }
        
        
        anomalie_agent_stock=anomalie_agent
 
        writeData(wb_anom_agents,paste("Tx non anomalie agents_stock"), x=anomalie_agent_stock, startRow=1, startCol=1)
                        addStyle(wb_anom_agents,paste("Tx non anomalie agents_stock"), headerStyle, cols=1:ncol(anomalie_agent), rows=1)
           
        if (nrow(anomalies_pp)!=0) {
          
          
                        anomalies_pp=reset_row_names(anomalies_pp)
                        expl=reset_row_names(anomalies_pp)

                        expl=expl[,-c(1:3)]
                        expl=reset_row_names(expl)

                        expl_anomalies=as.matrix(expl)
                        n_anorm_i= sum(grepl("ANOMALIE",expl_anomalies, ignore.case=T))

                        l=ncol(expl)-6
                        expl=expl[,c(1:l)]
                        expl=reset_row_names(expl)

                        total=ncol(expl)*nrow(expl) - length(which(expl==""))
                        taux_anomalie=floor(100*(1-n_anorm_i/total))

                                
                        taux_anomalie=unname(paste(taux_anomalie,"%",sep=""))

                         
                     

                         taux_anomalie_fil=data.frame(STOCK="",TAUX_NON_ANOMALIE=taux_anomalie, stringsAsFactors=FALSE)
                         taux_anomalie_fil_stock=reset_row_names(taux_anomalie_fil)

        }
                    


        writeData(wb_anom_agents,paste("Tx non anomalie BOA_",fil), x=taux_anomalie_fil_stock, startRow=4, startCol=1)
        addStyle(wb_anom_agents,paste("Tx non anomalie BOA_",fil), headerStyle, cols=1:ncol(taux_anomalie_fil_stock), rows=4)


   ### Anomalies par agence
          
    
            agents=unique(pp_ne$AGENCE)#("[[:alnum:]]", pp_ne$EXPL)=="TRUE"])

            anomalie_agent=data.frame(AGENT="",TAUX_NON_ANOMALIE="")
        
           taux_agences=matrix(,ncol=2)

           for(x in unique(pp_ne$AGENCE)) {

                     anomalie_agent=data.frame(AGENT="",TAUX_NON_ANOMALIE="")

                    agence=anomalies_pp_t[anomalies_pp_t$AGENCE==x,]
                  


                    if (nrow(agence!=0)) {


                        ### Anomalies par agents et par agence


                        agents_anom=unique(agence$EXPL)

                        anomalie_agent_t=lapply(agents_anom,function_anom_agent)

                        anomalie_agent=do.call("rbind",anomalie_agent_t)

                        anomalie_agent=anomalie_agent[!anomalie_agent$AGENT=="",]



                        writeData(wb_anom_agents,paste("Tx non anomalie agents_stock"), x=anomalie_agent, startRow=1, startCol=1)
                        addStyle(wb_anom_agents,paste("Tx non anomalie agents_stock"), headerStyle, cols=1:ncol(anomalie_agent), rows=1)

                        n_anorm=length(which(agence$ANOMALIE_AGE!="")) + length(which(agence$ANOMALIE_DATE_EER!="")) + length(which(agence$ANOMALIE_CIN!=""))

                  
                        expl=anomalies_pp[anomalies_pp$AGENCE==x,]

                        expl=expl[,-c(1:3)]

                        expl_anomalies=as.matrix(expl)
                        n_anorm_i= sum(grepl("ANOMALIE",expl_anomalies, ignore.case=T))

                        l=ncol(expl)-6
                        expl=expl[,c(1:l)]

                        total=ncol(expl)*nrow(expl) - length(which(expl==""))
                        taux_anomalie=floor(100*(1-n_anorm_i/total))

                                
                        taux_anomalie=paste(taux_anomalie,"%",sep="")

                         t1=c(paste("Agence",x, sep=" "),"Pourcentage")
                         t2=c("Taux de non anomalie", taux_anomalie)

                         taux_anomalie_t=as.data.frame(rbind(t1,t2))
                         colnames(taux_anomalie_t)=taux_anomalie_t[1,]
                         taux_anomalie_t=taux_anomalie_t[-1,]
                         
                     
                         taux_agences_i=c(paste0("Agence ",x),taux_anomalie)

                         taux_agences=rbind(taux_agences,taux_agences_i)
                         
                        taux_agences=as.data.frame(taux_agences)



                          ###### Taux Anomalie par agent

                         wb_agence=createWorkbook()
                         wb_anom_agence=createWorkbook()
                          wb_anom_agence_s=createWorkbook()

                    

                  
                          
                        colnames(taux_anomalie_t)[1]= paste("STOCK AGENCE",x)

                        colnames(anomalie_agent)[2]="TAUX_NON_ANOMALIE"
                        sheet_non_anom_s <- unique_sheet_name(wb_anom_agence_s, paste0(x,"_Taux de non anomalie"))
                        sheet_anom_stock <- unique_sheet_name(wb_agence, paste0(x,"_Anomalies stock"))
                        addWorksheet(wb_anom_agence_s, sheet_non_anom_s)


                                        # addWorksheet(wb_agence,paste0("RECAP AGENCE ",x))
                        # addWorksheet(wb_agence,paste0("RECAP AGENTS"))
                        addWorksheet(wb_agence, sheet_anom_stock)



                        writeData(wb_agence, sheet_anom_stock, x=agence, startRow=1, startCol=1)
                        addStyle(wb_agence, sheet_anom_stock, headerStyle, cols=1:ncol(agence), rows=1)

                        writeData(wb_anom_agence_s, sheet_non_anom_s, x=taux_anomalie_t, startRow=4, startCol=1)
                        

                        writeData(wb_anom_agence_s, sheet_non_anom_s, x=anomalie_agent, startRow=1, startCol=8)
                    
                                    
                               
                          
                            saveWorkbook(wb_anom_agence_s, paste(sep="",paste(chemin,fil,"//Anomalies par agence//",sep=""),"Agence_",paste(x)," stock.xlsx"), overwrite=T)

                                    saveWorkbook(wb_agence, paste(sep="",paste(chemin,fil,"//Contrôle de qualité//Contrôle qualité Stock//",sep=""),"Agence_",paste(x),".xlsx"), overwrite=T)

                            
                       }

                     
                       
                  }
         

        taux_agences=as.data.frame(taux_agences)
        colnames(taux_agences)=c("Agences","Taux d'anomalies - Stock")

        taux_agences=taux_agences[-1,]

        writeData(wb_anom_agents,paste("Tx non anomalie agences_stock"), x=taux_agences, startRow=1, startCol=1)
        addStyle(wb_anom_agents,paste("Tx non anomalie agences_stock"), headerStyle, cols=1:ncol(taux_agences), rows=1)


        writeData(wb_anom_agents,paste("Tx non anomalie agents_stock"), x=anomalie_agent, startRow=1, startCol=1)
        addStyle(wb_anom_agents,paste("Tx non anomalie agents_stock"), headerStyle, cols=1:ncol(anomalie_agent), rows=1)


       saveWorkbook(wb_anom_agents, paste(sep="",paste(chemin,fil,sep=""),"//Taux de non-anomalie BOA_",fil,".xlsx"), overwrite=T)

                ## PM

        agents_pm=unique(pm_ne$EXPL[grepl("[[:alnum:]]", pm_ne$EXPL)=="TRUE"])
        agents_null_pm=pm_ne[grepl("[[:alnum:]]", pm_ne$EXPL)=="FALSE",]

        etat_expl=data.frame(Agents="", `Nbre clients concernés`="", AGEC="",Capital="", CA = "", Resultat = "", RCSNO = "",CODAPE= "", ORIGINE_REV="", TEL=tel, `Taux de fiabilisation`="", Appréciation="")##`Taux à rattrapper`="")
        taux_filiale_pm_stock = lapply(agents_pm,taux_function_pm)
        
        taux_filiale_pm_stock=bind_results(taux_filiale_pm_stock, etat_expl)
        taux_filiale_pm_stock=taux_filiale_pm_stock[-which(taux_filiale_pm_stock$RCSNO==""),]
      

      
        taux_completude_stock_pm = data.frame(Agents=taux_filiale_pm_stock$Agents, Taux=taux_filiale_pm_stock$Taux.de.fiabilisation, Date=premier_jour_mois_precedent, flux_stock=rep("F", nrow(taux_filiale_pm_stock)), pp_pm=rep("M", nrow(taux_filiale_pm_stock)))





         taux_completude = rbind(taux_completude_pp,taux_completude_pm,taux_completude_stock_pp,taux_completude_stock_pm)

         write.csv2(taux_completude, paste(sep="",chemin,fil,"taux_",fil,".csv"), row.names=F)


          #### les taux d'appréciation

              #### les taux d'appréciation PM et PP combinés min(Txp,Txm)


                 #### les taux d'appréciation PM et PP combinés min(Txp,Txm)

        app_flux <- compute_app_flux(taux_filiale_t_stock, taux_filiale_pm_stock)
        app_flux <- app_flux[!(is.na(app_flux$Agents) | app_flux$Agents==""),]

        taux_app_flux=app_flux


              rm(taux_app_flux)

              

        taux_app_flux=data.frame(Agents=taux_filiale_t_stock$Agents,Taux_Completude=taux_filiale_t_stock$Taux.de.fiabilisation)

        colnames(anomalie_agent_stock)[1]="Agents"

         if ((is.null(str(anomalie_agent_stock$AGENT))=="TRUE")) {
          anomalie_agent=data.frame(Agents=anomalies_pp$EXPL, TAUX_NON_ANOMALIE=rep("100%",length(anomalies_pp$EXPL)))

      }



        taux_app_flux=left_join(taux_app_flux,anomalie_agent_stock,by="Agents")

        taux_app_flux=taux_app_flux[,-4]

        taux_app_flux=left_join(taux_app_flux,cp_flux,by="Agents")

        taux_app_flux$TAUX_NON_ANOMALIE=as.numeric(gsub("%","",taux_app_flux$TAUX_NON_ANOMALIE))

        taux_app_flux$Note_1=""

 


        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE<=80 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Très bien"]="Insatisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE<=80 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Bien"]="Insatisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE<=80 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Moyen"]="Insatisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE<=80 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Passable"]="Insatisfaisant"


        taux_app_flux$Note_1[(taux_app_flux$TAUX_NON_ANOMALIE<100 & taux_app_flux$TAUX_NON_ANOMALIE>80) & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Très bien"]="Satisfaisant"
        taux_app_flux$Note_1[(taux_app_flux$TAUX_NON_ANOMALIE<100 & taux_app_flux$TAUX_NON_ANOMALIE>80) & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Bien"]="Satisfaisant"
        taux_app_flux$Note_1[(taux_app_flux$TAUX_NON_ANOMALIE<100 & taux_app_flux$TAUX_NON_ANOMALIE>80) & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Moyen"]="Insatisfaisant"
        taux_app_flux$Note_1[(taux_app_flux$TAUX_NON_ANOMALIE<100 & taux_app_flux$TAUX_NON_ANOMALIE>80) & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Passable"]="Insatisfaisant"

        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE==100 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Très bien"]="Très satisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE==100 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Bien"]="Satisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE==100 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Moyen"]="Satisfaisant"
        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE==100 & taux_app_flux$NOTE_CONTROLE_PERMANANT=="Passable"]="Insatisfaisant"


        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE<=80 & (is.na(taux_app_flux$NOTE_CONTROLE_PERMANANT)=="TRUE" | taux_app_flux$NOTE_CONTROLE_PERMANANT=="")]="Insatisfaisant"

        taux_app_flux$Note_1[(taux_app_flux$TAUX_NON_ANOMALIE < 100 & taux_app_flux$TAUX_NON_ANOMALIE > 80) & (is.na(taux_app_flux$NOTE_CONTROLE_PERMANANT)=="TRUE" | taux_app_flux$NOTE_CONTROLE_PERMANANT=="") ]="Satisfaisant"

        taux_app_flux$Note_1[taux_app_flux$TAUX_NON_ANOMALIE==100 & (is.na(taux_app_flux$NOTE_CONTROLE_PERMANANT)=="TRUE" | taux_app_flux$NOTE_CONTROLE_PERMANANT=="")]="Très satisfaisant"

       
        note_cp=data.frame(NOTE_CONTROLE_PERMANANT=taux_app_flux$NOTE_CONTROLE_PERMANANT)
        note_cp$NOTE_CONTROLE_PERMANANT[is.na(note_cp$NOTE_CONTROLE_PERMANANT)]=0

        note_cp[note_cp$NOTE_CONTROLE_PERMANANT=="Très bien"]=4
        note_cp[note_cp$NOTE_CONTROLE_PERMANANT=="Bien"]=3
        note_cp[note_cp$NOTE_CONTROLE_PERMANANT=="Moyen"]=2
        note_cp[note_cp$NOTE_CONTROLE_PERMANANT=="Passable"]=1

        note_filiale_fll=mean((note_cp$NOTE_CONTROLE_PERMANANT), na.rm=FALSE)

        note_finale=data.frame(Filiale=fil, Notation=note_filiale_fll, Date=premier_jour_mois_precedent)
        note_groupe_stock=rbind(note_finale,note_groupe_stock)

        write.csv2(note_groupe,paste0(chemin,"note_groupe_stock.csv"))
       ## Note Finale

         if (trimestre_actuel=="1") {

          taux_app_flux$Appreciation_Globale=""

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=5 & taux_app_flux$Note_1=="Très satisfaisant"]="Faible++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=5 & taux_app_flux$Note_1=="Satisfaisant"]="Faible+"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=5 & taux_app_flux$Note_1=="Insatisfaisant"]="Faible-"

          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>5 & taux_app_flux$Taux_Completude <=30) & taux_app_flux$Note_1=="Très satisfaisant"]="Moyen++"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>5 & taux_app_flux$Taux_Completude <=30) & taux_app_flux$Note_1=="Satisfaisant"]="Moyen+"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>5 & taux_app_flux$Taux_Completude <=30) & taux_app_flux$Note_1=="Insatisfaisant"]="Moyen-"

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>30 & taux_app_flux$Note_1=="Très satisfaisant"]="Bon++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>30 & taux_app_flux$Note_1=="Satisfaisant"]="Bon+"
           taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>30 & taux_app_flux$Note_1=="Insatisfaisant"]="Bon-"
         }

           if (trimestre_actuel=="2") {

          taux_app_flux$Appreciation_Globale=""

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=30 & taux_app_flux$Note_1=="Très satisfaisant"]="Faible++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=30 & taux_app_flux$Note_1=="Satisfaisant"]="Faible+"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=30 & taux_app_flux$Note_1=="Insatisfaisant"]="Faible-"

          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>30 & taux_app_flux$Taux_Completude <=60) & taux_app_flux$Note_1=="Très satisfaisant"]="Moyen++"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>30 & taux_app_flux$Taux_Completude <=60) & taux_app_flux$Note_1=="Satisfaisant"]="Moyen+"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>30 & taux_app_flux$Taux_Completude <=60) & taux_app_flux$Note_1=="Insatisfaisant"]="Moyen-"

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>60 & taux_app_flux$Note_1=="Très satisfaisant"]="Bon++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>60 & taux_app_flux$Note_1=="Satisfaisant"]="Bon+"
           taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>60 & taux_app_flux$Note_1=="Insatisfaisant"]="Bon-"
         }

           if (trimestre_actuel=="3") {

          taux_app_flux$Appreciation_Globale=""

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=60 & taux_app_flux$Note_1=="Très satisfaisant"]="Faible++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=60 & taux_app_flux$Note_1=="Satisfaisant"]="Faible+"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=60 & taux_app_flux$Note_1=="Insatisfaisant"]="Faible-"

          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>60 & taux_app_flux$Taux_Completude <=90) & taux_app_flux$Note_1=="Très satisfaisant"]="Moyen++"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>60 & taux_app_flux$Taux_Completude <=90) & taux_app_flux$Note_1=="Satisfaisant"]="Moyen+"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>60 & taux_app_flux$Taux_Completude <=90) & taux_app_flux$Note_1=="Insatisfaisant"]="Moyen-"

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>90 & taux_app_flux$Note_1=="Très satisfaisant"]="Bon++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>90 & taux_app_flux$Note_1=="Satisfaisant"]="Bon+"
           taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>90 & taux_app_flux$Note_1=="Insatisfaisant"]="Bon-"
         }

           if (trimestre_actuel=="4") {

          taux_app_flux$Appreciation_Globale=""

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=65 & taux_app_flux$Note_1=="Très satisfaisant"]="Faible++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=65 & taux_app_flux$Note_1=="Satisfaisant"]="Faible+"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude<=65 & taux_app_flux$Note_1=="Insatisfaisant"]="Faible-"

          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>55 & taux_app_flux$Taux_Completude <=95) & taux_app_flux$Note_1=="Très satisfaisant"]="Moyen++"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>65 & taux_app_flux$Taux_Completude <=95) & taux_app_flux$Note_1=="Satisfaisant"]="Moyen+"
          taux_app_flux$Appreciation_Globale[(taux_app_flux$Taux_Completude>65 & taux_app_flux$Taux_Completude <=95) & taux_app_flux$Note_1=="Insatisfaisant"]="Moyen-"

          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>95 & taux_app_flux$Note_1=="Très satisfaisant"]="Bon++"
          taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>95 & taux_app_flux$Note_1=="Satisfaisant"]="Bon+"
           taux_app_flux$Appreciation_Globale[taux_app_flux$Taux_Completude>95 & taux_app_flux$Note_1=="Insatisfaisant"]="Bon-"
         }


        taux_app_flux=taux_app_flux[,-5]
        taux_app_flux$Taux_Completude=paste(taux_app_flux$Taux_Completude,"%")
        taux_app_flux$TAUX_NON_ANOMALIE=paste(taux_app_flux$TAUX_NON_ANOMALIE,"%")

         taux_app_flux$Mesure=""

         taux_app_flux$Mesure[taux_app_flux$Appreciation_Globale=="Faible++" | taux_app_flux$Appreciation_Globale=="Faible+" | taux_app_flux$Appreciation_Globale=="Moyen++" 
                                          |taux_app_flux$Appreciation_Globale=="Faible+"]="Demande d’explication et décote sur le bonus si motif infondé"

        taux_app_flux$Mesure[taux_app_flux$Appreciation_Globale=="Faible-" | taux_app_flux$Appreciation_Globale=="Moyen-" | taux_app_flux$Appreciation_Globale=="Bon-"] = "Demande d’explication avec sanction forte et décote sur le bonus si motif infondé"

        taux_app_flux$Mesure[taux_app_flux$Appreciation_Globale=="Bon++" | taux_app_flux$Appreciation_Globale=="Bon+"] = "Impact positif sur le bonus"

        taux_app_flux=taux_app_flux[taux_app_flux$Mesure!="",]

        colnames(taux_app_flux)=c("Agents","Taux de complétude","Taux de non-anomalie","Note Contrôle Permanent","Appréciation Globale","Mesures de sanctions")
  
       
              
                 wb_note_flux=createWorkbook()
                 addWorksheet(wb_note_flux,"Appréciation")
                 writeData(wb_note_flux,"Appréciation", x=taux_app_flux, startRow=1, startCol=1)

                  
                      

                 addStyle(wb_note_flux,"Appréciation",headerStyle, cols=1:ncol(taux_app_flux), rows=1)



                    
                 saveWorkbook(wb_note_flux, paste(sep="",paste(chemin,fil,"//Contrôle de qualité//Contrôle qualité Stock//",sep=""),"Notation des agents_Stock",".xlsx"), overwrite=T)
               




       addWorksheet(wb_anomalies_fliale,"Appréciation agents_stock")
       writeData(wb_anomalies_fliale,"Appréciation agents_stock", x=taux_app_flux, startRow=1, startCol=1)

       addStyle(wb_anomalies_fliale,"Appréciation agents_stock",headerStyle, cols=1:ncol(taux_app_flux), rows=1)

       saveWorkbook(wb_anomalies_fliale, paste(sep="",paste(chemin,fil,sep=""),"//Appréciation globale BOA_",fil,".xlsx"), overwrite=T)




  

    rm(taux_app_flux)

        ### Creation du fichier Excel de suivi
        wb=createWorkbook()

  
     

 ### Resume filiale
 

k=ncol(tableau_suivi)



   ### Taux fiabilisation filiale

         wb_filiale=createWorkbook()
         addWorksheet(wb_filiale,"Récapitulatif")


   ### Taux fiabilisation filiale

         wb_filiale=createWorkbook()
         addWorksheet(wb_filiale,"Récapitulatif")

           ### recap stock          
             writeData(wb_filiale,"Récapitulatif", x=tableau_suivi_t, startRow=5, startCol=3)
             addStyle(wb_filiale,"Récapitulatif",headerStyle,cols=3:5, rows=5)
               ### recap flux          
             writeData(wb_filiale,"Récapitulatif", x=tableau_suivi_stock_t, startRow=5, startCol=3)
             addStyle(wb_filiale,"Récapitulatif",headerStyle,cols=7:9, rows=5)
             
           
    


        ### Sheet Flux PP
        addWorksheet(wb,"Flux PP")

        writeData(wb,"Flux PP", x=taux_filiale_t, startRow=1, startCol=1)

        k=ncol(taux_filiale_t)

        headerStyle <- createStyle(
        fontSize = 14, fontColour = "white", halign = "left",
        fgFill = "#09982E", border = "TopBottom", borderColour = "black"
        )

        addStyle(wb,"Flux PP",headerStyle,cols=1:k, rows=1)


        bonStyle <- createStyle(halign = "right",
        fgFill = "#298904"
        )
        moyenStyle <- createStyle(halign = "right",
        fgFill = "#F8DF19"
        )
        lowStyle <- createStyle(halign = "right",
        fgFill = "#D90A0A"
        )
        apply_status_style(wb, "Flux PP", taux_filiale_t, value_col = 14)


      ### Recap Sheet Flux PP
        addWorksheet(wb_recap,"Agent Flux PP")


        writeData(wb_recap,"Agent Flux PP", x=taux_filiale_t, startRow=1, startCol=1)

        k=ncol(taux_filiale_t)

       
        addStyle(wb_recap,"Agent Flux PP",headerStyle,cols=1:k, rows=1)


        apply_status_style(wb_recap, "Agent Flux PP", taux_filiale_t, value_col = 14)



         ### Sheet Flux 
         
              if (is.null(taux_filiale_pm)=="FALSE") {
                    addWorksheet(wb,"Flux PM")

                    writeData(wb,"Flux PM", x=taux_filiale_pm, startRow=1, startCol=1)

                    k=ncol(taux_filiale_pm)

                    headerStyle <- createStyle(
                    fontSize = 14, fontColour = "white", halign = "left",
                    fgFill = "#09982E", border = "TopBottom", borderColour = "black"
                    )

                    addStyle(wb,"Flux PM",headerStyle,cols=1:k, rows=1)


                    apply_status_style(wb, "Flux PM", taux_filiale_pm, value_col = 12, col_good = 9, col_mid = 9, col_low = 12)

              }

         ### Recap Sheet Flux PM

      if (is.null(taux_filiale_pm)=="FALSE") {

        addWorksheet(wb_recap,"Agent Flux PM")

        writeData(wb_recap,"Agent Flux PM", x=taux_filiale_pm, startRow=1, startCol=1)

        k=ncol(taux_filiale_pm)

        headerStyle <- createStyle(
        fontSize = 14, fontColour = "white", halign = "left",
        fgFill = "#09982E", border = "TopBottom", borderColour = "black"
        )

        addStyle(wb_recap,"Agent Flux PM",headerStyle,cols=1:k, rows=1)


        apply_status_style(wb_recap, "Agent Flux PM", taux_filiale_pm, value_col = 12)

              }

        ### Sheet Stock PP
        addWorksheet(wb,"Stock PP")


        writeData(wb,"Stock PP", x=taux_filiale_t_stock, startRow=1, startCol=1)

        k=ncol(taux_filiale_t_stock)

        headerStyle <- createStyle(
        fontSize = 14, fontColour = "white", halign = "left",
        fgFill = "#09982E", border = "TopBottom", borderColour = "black"
        )

        addStyle(wb,"Stock PP",headerStyle,cols=1:k, rows=1)


        bonStyle <- createStyle(halign = "right",
        fgFill = "#298904"
        )
        moyenStyle <- createStyle(halign = "right",
        fgFill = "#F8DF19"
        )
        lowStyle <- createStyle(halign = "right",
        fgFill = "#D90A0A"
        )

        apply_status_style(wb, "Stock PP", taux_filiale_t_stock, value_col = 14)

          ### Recap Sheet Stock PP
        addWorksheet(wb_recap,"Agent Stock PP")


        writeData(wb_recap,"Agent Stock PP", x=taux_filiale_t_stock, startRow=1, startCol=1)

        k=ncol(taux_filiale_t_stock)

        headerStyle <- createStyle(
        fontSize = 14, fontColour = "white", halign = "left",
        fgFill = "#09982E", border = "TopBottom", borderColour = "black"
        )

        addStyle(wb_recap,"Agent Stock PP",headerStyle,cols=1:k, rows=1)


        bonStyle <- createStyle(halign = "right",
        fgFill = "#298904"
        )
        moyenStyle <- createStyle(halign = "right",
        fgFill = "#F8DF19"
        )
        lowStyle <- createStyle(halign = "right",
        fgFill = "#D90A0A"
        )

        apply_status_style(wb_recap, "Agent Stock PP", taux_filiale_t_stock, value_col = 14)

         ### Sheet Stock PM
        addWorksheet(wb,"Stock PM")

        writeData(wb,"Stock PM", x=taux_filiale_pm_stock, startRow=1, startCol=1)

        k=ncol(taux_filiale_pm_stock)

        headerStyle <- createStyle(
        fontSize = 14, fontColour = "white", halign = "left",
        fgFill = "#09982E", border = "TopBottom", borderColour = "black"
        )

        addStyle(wb,"Stock PM",headerStyle,cols=1:k, rows=1)


        apply_status_style(wb, "Stock PM", taux_filiale_pm_stock, value_col = 12)


         ### Recap Stock PM
        addWorksheet(wb_recap," Agent Stock PM")

        writeData(wb_recap," Agent Stock PM", x=taux_filiale_pm_stock, startRow=1, startCol=1)

        k=ncol(taux_filiale_pm_stock)

        headerStyle <- createStyle(
        fontSize = 14, fontColour = "white", halign = "left",
        fgFill = "#09982E", border = "TopBottom", borderColour = "black"
        )

        addStyle(wb_recap," Agent Stock PM",headerStyle,cols=1:k, rows=1)


        apply_status_style(wb_recap, " Agent Stock PM", taux_filiale_pm_stock, value_col = 9)


            saveWorkbook(wb, paste(sep="",paste(chemin,fil,"//",sep=""),"Rapport des taux de complétude par agent de ",sigle,".xlsx"), overwrite=T)
            
              saveWorkbook(wb_filiale, paste(sep="",paste(chemin,fil,"//",sep=""),"Rapport du taux de complétude de la filiale ",sigle,".xlsx"), overwrite=T)
          
              saveWorkbook(wb_recap, paste(sep="",paste(chemin,fil,"//",sep=""),"Taux de complétude BOA_",sigle,".xlsx"), overwrite=T)


         
            
            if (exists("tableau_fiabilisation")=="TRUE") {
              cat("######################################################################################\n")
              cat("######### Les fichiers des suivi de ",sigle," par agence sont générés avec sucès ######\n")
              cat("######################################################################################\n")
            } else {
              cat("######################################################################################\n")
              cat("######### ERREUR: Les fichiers des suivi de ",sigle," par agence ne sont pas générés ####\n")
              cat("######################################################################################\n")
              
            }


              cat("######################################################################################\n")
              cat("######### Génération du rapport de suivi de ",sigle," pour la Direction générale ######\n")
              cat("######################################################################################\n")




            ## les graphiques Fiabilisation PP

          suivi_fiabilisation_i=as.data.frame(c(tableau_suivi_t[,-1],tableau_suivi_stock_t[,-1],as.Date(premier_jour_mois_courant)-1))
          colnames(suivi_fiabilisation_i)=c("Flux PM","Flux PP","Stock PM", "Stock PP","Date")
          suivi_fiabilisation_i$Date=as.Date(suivi_fiabilisation_i$Date)
          suivi_fiabilisation_i=suivi_fiabilisation_i[-1,]

         
          suivi_fiabilisation$Date=parse_date_any(suivi_fiabilisation$Date)
            
          colnames(suivi_fiabilisation)=c("Flux PM","Flux PP","Stock PM", "Stock PP","Date")

          suivi_fiabilisation=rbind(suivi_fiabilisation,suivi_fiabilisation_i)

      
          suivi_fiabilisation_out <- suivi_fiabilisation
          suivi_fiabilisation_out$Date <- format(suivi_fiabilisation_out$Date, "%d/%m/%Y")
          suivi_fiabilisation_out =unique(suivi_fiabilisation_out)


          write.csv2(suivi_fiabilisation_out, paste0(chemin,fil,"//suivi_fiabilisation.txt"))
          
          write.csv2(suivi_fiabilisation_out, paste0(chemin,fil,"//data//suivi_fiabilisation_",fil,".csv"), row.names=FALSE)


          


  ## les graphiques Anomalies
  suivi_anomalie_i=as.data.frame(cbind(taux_anomalie_fil_flux[,2],taux_anomalie_fil_stock[,2],as.Date(premier_jour_mois_courant)-1))
  colnames(suivi_anomalie_i)=c("Flux PP","Stock PP","Date")
  suivi_anomalie_i$Date=as.Date(as.numeric(suivi_anomalie_i$Date))

  suivi_anomalie$Date=parse_date_any(suivi_anomalie$Date)
       
  colnames(suivi_anomalie)=c("Flux PP","Stock PP","Date")
  suivi_anomalie=rbind(suivi_anomalie,suivi_anomalie_i)


  suivi_anomalie_out <- suivi_anomalie
  suivi_anomalie_out$Date <- format(suivi_anomalie_out$Date, "%d/%m/%Y")
  suivi_anomalie_out =unique(suivi_anomalie_out)
  write.csv2(suivi_anomalie_out, paste0(chemin,fil,"//suivi_anomalie.txt"))
  write.csv2(suivi_anomalie_out, paste0(chemin,fil,"//data//suivi_anomalie_",fil,".csv"), row.names=FALSE)



     ## Les taux de complétudepar agent flux et stock

          flux_pp=read_excel(paste0(chemin,fil,"//Rapport des taux de complétude par agent de BOA_",fil,".xlsx"), sheet=1)

          flux_pp=data.frame(Agents=flux_pp$Agents,Taux=flux_pp$Taux.de.fiabilisation,Date=rep(premier_jour_mois_precedent,nrow(flux_pp)), flux_stock=rep("F",nrow(flux_pp)), pp_pm=rep("P",nrow(flux_pp)))

          flux_pm=read_excel(paste0(chemin,fil,"//Rapport des taux de complétude par agent de BOA_",fil,".xlsx"), sheet=2)
          flux_pm=data.frame(Agents=flux_pm$Agents,Taux=flux_pm$Taux.de.fiabilisation,Date=rep(premier_jour_mois_precedent,nrow(flux_pm)), flux_stock=rep("F",nrow(flux_pm)), pp_pm=rep("M",nrow(flux_pm)))


          stock_pp=read_excel(paste0(chemin,fil,"//Rapport des taux de complétude par agent de BOA_",fil,".xlsx"), sheet=3)
          stock_pp=data.frame(Agents=stock_pp$Agents,Taux=stock_pp$Taux.de.fiabilisation,Date=rep(premier_jour_mois_precedent,nrow(stock_pp)), flux_stock=rep("S",nrow(stock_pp)), pp_pm=rep("P",nrow(stock_pp)))

          stock_pm=read_excel(paste0(chemin,fil,"//Rapport des taux de complétude par agent de BOA_",fil,".xlsx"), sheet=4)
          stock_pm=data.frame(Agents=stock_pm$Agents,Taux=stock_pm$Taux.de.fiabilisation,Date=rep(premier_jour_mois_precedent,nrow(stock_pm)), flux_stock=rep("S",nrow(stock_pm)), pp_pm=rep("M",nrow(stock_pm)))

          write.csv2(rbind(flux_pp,flux_pm,stock_pp,stock_pm), paste0(chemin,fil,"//data//taux_",fil,".csv"), row.names=FALSE)


          

     data_dir <- paste0(chemin, fil, "//data//")

dossier_A <- paste0(chemin,fil,"//data//")
dossier_B <- "C://Fiabilisation KYC//Python//data//"


fichiers <- c(
  paste0("anomalies_", fil, ".csv"),
  paste0("taux_", fil, ".csv"),
  paste0("suivi_fiabilisation_", fil, ".csv"),
  paste0("suivi_anomalie_", fil, ".csv"),
  paste0("scoring_", fil, ".csv"),
  paste0("agents_", fil, ".csv"),
  paste0("pp_", fil, "_STOCK_F.csv"),
  paste0("pm_", fil, "_STOCK_F.csv"),
  paste0("pp_", fil, "_STOCK.csv"),
  paste0("pm_", fil, "_STOCK.csv")
)

# 3. Construire les chemins complets
chemins_sources <- file.path(dossier_A, fichiers)
chemins_destinations <- file.path(dossier_B, fichiers)

# 4. Copier les fichiers
# Utilisation de 'overwrite = TRUE' si vous voulez remplacer les fichiers existants dans B
file.copy(from = chemins_sources, to = chemins_destinations, overwrite = TRUE)



}



for (fil in filiale){
  tryCatch(
    production(fil),
    error = function(e) {
      message("Erreur filiale ", fil, " : ", e$message)
    }
  )
}