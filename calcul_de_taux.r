### MODIF_VISIBLE_CODEX_2026_04_23_RENDU_FINAL

#####-----------------------IMPORTATION DES LIBRAIRIES-------------###########
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

#####-----------------------CONFIG ET FONCTIONS-------------###########
chemin <- "C://Users//mamsylla//OneDrive - BANK OF AFRICA (1)//data//"

# Lecture des prérequis
prerequis <- read.csv2(paste0(chemin, "prerequis.csv"), header = FALSE)
colnames(prerequis) <- c("infos", "argument", "LIB_ETUDIANT", "LIB_MINEUR")

premier_jour_mois_courant <- as.character(floor_date(Sys.Date(), "month"))
premier_jour_mois_precedent <- as.character(as.Date(premier_jour_mois_courant) %m-% months(1))



filiale <- prerequis$infos[prerequis$argument == "y"]

# Fonctions utilitaires de nettoyage
is_alphanumeric <- function(x) {
  if (is.character(x)) {
    x2 <- suppressWarnings(iconv(x, from = "", to = "UTF-8", sub = ""))
    bad <- is.na(x2); if (any(bad)) x2[bad] <- suppressWarnings(iconv(x[bad], from = "latin1", to = "UTF-8", sub = ""))
    x <- x2
  }
  grepl("[a-zA-Z]", x, useBytes = TRUE) | grepl("[0-9]", x, useBytes = TRUE)
}

is_rep <- function(x) {
  (grepl("XX", x) & nchar(x)==2) | (grepl("RAS", x) & nchar(x)==3) | (grepl("R.A.S.", x) & nchar(x)==6) | (grepl("R.A.S", x) & nchar(x)==5) | nchar(x)==1
}

clean_colnames <- function(data) {
  names(data) <- gsub("^[\\xef\\xbb\\xbf\\u00ef\\u00bb\\u00bf]|^ï\\.\\.\\.?|^ï\\.\\.|^ï\\.\\xef", "", names(data))
  return(data)
}

clean_and_mark_anomalies <- function(df, start_col = 4) {
  if (is.null(df) || ncol(df) < start_col) return(df)
  df[] <- lapply(df, function(x) if (is.character(x)) trimws(x) else x)
  cols <- start_col:ncol(df)
  df[cols] <- Map(function(x, nm) {
    x[is.na(x)] <- ""
    rep_idx <- is_rep(x)
    if (any(rep_idx, na.rm = TRUE)) x[rep_idx] <- paste("ANOMALIE", nm)
    x
  }, df[cols], names(df)[cols])
  df
}

# Fonctions de calcul des taux
to_pct <- function(x) {
  x_num <- suppressWarnings(as.numeric(x))
  ifelse(is.na(x_num), "N/A", paste0(floor(x_num), "%"))
}

champ_rate <- function(df, champ) {
  if (is.null(df) || nrow(df) == 0 || !(champ %in% colnames(df))) return(NA_real_)
  n_vide <- nrow(df[trimws(as.character(df[[champ]])) == "" | is.na(df[[champ]]), , drop = FALSE])
  floor(100 - (n_vide / nrow(df) * 100))
}

global_rate <- function(df, fields) {
  if (is.null(df) || nrow(df) == 0) return(NA_real_)
  total_cells <- length(fields) * nrow(df)
  n_empty <- sum(sapply(df[, intersect(fields, colnames(df)), drop=FALSE], function(x) sum(trimws(as.character(x)) == "" | is.na(x))))
  floor(100 * (1 - (n_empty / total_cells)))
}

client_completion_rate <- function(df, fields) {
  if (is.null(df) || nrow(df) == 0) return(NA_real_)
  block <- df[, intersect(fields, colnames(df)), drop = FALSE]
  row_has_empty <- Reduce(`|`, lapply(block, function(x) trimws(as.character(x)) == "" | is.na(x)))
  floor(100 * (1 - (sum(row_has_empty) / nrow(df))))
}

# --- FONCTION DE STYLE (RENDU EXACT DE L'IMAGE) ---
style_ft_exact <- function(df) {
  ft <- flextable(df)
  
  # Fusion verticale de la première colonne (Libellés de groupe)
  ft <- merge_v(ft, j = 1) %>% valign(j = 1, valign = "center")
  
  # En-tête : Vert foncé, texte blanc, gras
  ft <- bg(ft, part = "header", bg = "#00965E") %>% 
        color(part = "header", color = "white") %>% 
        bold(part = "header", bold = TRUE)
  
  # Alignements
  ft <- align(ft, align = "center", part = "header")
  ft <- align(ft, j = 1:2, align = "left", part = "body")
  ft <- align(ft, j = 3:4, align = "center", part = "body")
  
  # Lignes de synthèse du bas : Gras + Alignement spécifique
  n_rows <- nrow(df)
  ft <- bold(ft, i = (n_rows-1):n_rows, bold = TRUE)
  ft <- align(ft, i = (n_rows-1):n_rows, j = 2, align = "right") # Aligne "Approche par..." à droite
  
  # Coloration conditionnelle Orange Rose (#F4B084)
  # Condition Flux < 100%
  ft <- bg(ft, j = "Flux (3)", 
           i = ~ as.numeric(gsub("%", "", `Flux (3)`)) < 100, 
           bg = "#F4B084", part = "body")
  
  # Condition Stock < 90%
  ft <- bg(ft, j = "Stock (4)", 
           i = ~ as.numeric(gsub("%", "", `Stock (4)`)) < 90, 
           bg = "#F4B084", part = "body")
  
  # Bordures noires fines (style image)
  ft <- border_outer(ft, border = fp_border(color = "black", width = 1))
  ft <- border_inner_h(ft, border = fp_border(color = "black", width = 0.5))
  ft <- border_inner_v(ft, border = fp_border(color = "black", width = 0.5))
  
  # Tailles et dimensions compactes pour une slide 10 x 5.625 pouces
  ft <- fontsize(ft, size = 9, part = "all")
  ft <- padding(ft, padding.top = 1, padding.bottom = 1, padding.left = 2, padding.right = 2, part = "all")
  ft <- height_all(ft, height = 0.24, part = "all")
  ft <- width(ft, j = 1, width = 2.1)
  ft <- width(ft, j = 2, width = 4.25)
  ft <- width(ft, j = 3, width = 1.5)
  ft <- width(ft, j = 4, width = 1.5)
  
  return(ft)
}

agent_completion_rates <- function(df, fields) {
  if (is.null(df) || nrow(df) == 0 || !("EXPL" %in% colnames(df))) return(numeric(0))
  agents <- sort(unique(trimws(as.character(df$EXPL))))
  agents <- agents[agents != "" & !is.na(agents)]
  rates <- sapply(agents, function(agent) {
    global_rate(df[trimws(as.character(df$EXPL)) == agent, , drop = FALSE], fields)
  })
  as.numeric(rates[!is.na(rates)])
}

agent_distribution_row <- function(rates) {
  labels <- c("[0, 50%]", "]50% , 60%]", "]60% , 80%]", "]80% , 100%]")
  if (length(rates) == 0) return(setNames(rep("0%", length(labels)), labels))
  cuts <- cut(rates, breaks = c(0, 50, 60, 80, 100), include.lowest = TRUE, right = TRUE, labels = labels)
  counts <- table(factor(cuts, levels = labels))
  setNames(paste0(floor(100 * as.numeric(counts) / length(rates)), "%"), labels)
}

style_slide5_table <- function(df, widths = NULL) {
  ft <- flextable(df)
  ft <- bg(ft, part = "header", bg = "#00965E") %>%
    color(part = "header", color = "white") %>%
    bold(part = "header", bold = TRUE)
  ft <- fontsize(ft, size = 9, part = "all")
  ft <- padding(ft, padding.top = 1, padding.bottom = 1, padding.left = 2, padding.right = 2, part = "all")
  ft <- align(ft, align = "center", part = "all")
  ft <- border_outer(ft, border = fp_border(color = "black", width = 1))
  ft <- border_inner_h(ft, border = fp_border(color = "black", width = 0.5))
  ft <- border_inner_v(ft, border = fp_border(color = "black", width = 0.5))
  if (!is.null(widths)) {
    for (j in seq_along(widths)) ft <- width(ft, j = j, width = widths[j])
  }
  ft
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


#####-----------------------BOUCLE DE TRAITEMENT-------------###########

for (fil in filiale) {
  sigle <- paste0("BOA_", fil)
  ppt <- read_pptx(paste0(chemin, "Template rapport KYC.pptx"))
  

    # 0. Configuration des libellés EXACTS de l'image
  pp_fields <- c("PAYNAIS","PROFESSION","SALAIRE","NUMID","CODAPE","TEL","DATNAIS","ADRESSE","DATVALID","ORIGINE_REVENU")
  pp_labels <- c("Lieu de Naissance","Profession","Salaire","NIN","Code agent économique","Téléphone","Adresse","Date de naissance","Date de validité CIN","Origine du revenu")
  
  pm_fields <- c("CODAPE","AGEC","CAPITAL","CA","RESULTAT","RCSNO","ORIGINE_REVENU","TEL")
  pm_labels <- c("Secteur d'activité","Code agent économique","Capital social","Chiffre d'affaires","Résultat net","Numéro de registre de commerce","Origine du revenu","Téléphone")

  # 1. Chargement et nettoyage des données (PP et PM)
  pp_ne <- read.csv2(paste0(chemin, fil, "//data//pp_", fil, "_STOCK.csv"), fileEncoding = "UTF-8-BOM") %>% clean_colnames()
  pp_ne$AGENCE <- as.numeric(pp_ne$AGENCE)
  pp_ne$AGENCE=as.numeric(pp_ne$AGENCE)
  colnames(pp_ne) <- toupper(colnames(pp_ne))
  
  pm_ne <- read.csv2(paste0(chemin, fil, "//data//pm_", fil, "_STOCK.csv"), fileEncoding = "UTF-8-BOM") %>% clean_colnames()
  pm_ne$AGENCE <- as.numeric(pm_ne$AGENCE)
   pm_ne=select_pm_fields(pm_ne, pm_fields)
  colnames(pm_ne) <- toupper(colnames(pm_ne))
  pm_exclure <- pm_ne %>% filter(trimws(toupper(AGEC)) %in% c("ORG", "ISB"))
  pm_ne <- pm_ne %>% filter(!(trimws(toupper(AGEC)) %in% c("ORG", "ISB")))
  
  # Correction EXPL et Marquage Anomalies
  pp_ne$EXPL[is_alphanumeric(pp_ne$EXPL) == FALSE] <- paste0("DIR_AGENCE_", pp_ne$AGENCE[is_alphanumeric(pp_ne$EXPL) == FALSE])
  pm_ne$EXPL[is_alphanumeric(pm_ne$EXPL) == FALSE] <- paste0("DIR_AGENCE_", pm_ne$AGENCE[is_alphanumeric(pm_ne$EXPL) == FALSE])
  pp_ne <- clean_and_mark_anomalies(pp_ne, start_col = 4)
  pm_ne <- clean_and_mark_anomalies(pm_ne, start_col = 4)
  
  # Filtre Flux
  pp_flux <- pp_ne %>% filter(DATOUV >= as.Date(premier_jour_mois_precedent), DATOUV < as.Date(premier_jour_mois_courant))
  pm_flux <- pm_ne %>% filter(DATOUV >= as.Date(premier_jour_mois_precedent), DATOUV < as.Date(premier_jour_mois_courant))
  

  # 3. Construction des Dataframes pour PP
  pp_table_ppt <- data.frame(
    Col1 = c(rep("Taux par champs", length(pp_labels)), rep("Taux de complétude global", 2)),
    Champs = c(pp_labels, "Approche par champs (1)", "Approche par clients (2)"),
    Flux = c(sapply(pp_fields, function(f) to_pct(champ_rate(pp_flux, f))), 
             to_pct(global_rate(pp_flux, pp_fields)), 
             to_pct(client_completion_rate(pp_flux, pp_fields))),
    Stock = c(sapply(pp_fields, function(f) to_pct(champ_rate(pp_ne, f))), 
              to_pct(global_rate(pp_ne, pp_fields)), 
              to_pct(client_completion_rate(pp_ne, pp_fields))),
    stringsAsFactors = FALSE
  )
  colnames(pp_table_ppt) <- c(" ", "Champs", "Flux (3)", "Stock (4)")

  # 4. Construction des Dataframes pour PM
  pm_table_ppt <- data.frame(
    Col1 = c(rep("Taux par champs", length(pm_labels)), rep("Taux de complétude global", 2)),
    Champs = c(pm_labels, "Approche par champs (1)", "Approche par clients (2)"),
    Flux = c(sapply(pm_fields, function(f) to_pct(champ_rate(pm_flux, f))), 
             to_pct(global_rate(pm_flux, pm_fields)), 
             to_pct(client_completion_rate(pm_flux, pm_fields))),
    Stock = c(sapply(pm_fields, function(f) to_pct(champ_rate(pm_ne, f))), 
              to_pct(global_rate(pm_ne, pm_fields)), 
              to_pct(client_completion_rate(pm_ne, pm_fields))),
    stringsAsFactors = FALSE
  )
  colnames(pm_table_ppt) <- c(" ", "Champs", "Flux (3)", "Stock (4)")

  # 5. Application du style et Exportation
  ft_pp <- style_ft_exact(pp_table_ppt)
  ft_pm <- style_ft_exact(pm_table_ppt)

  if (length(ppt) < 5) {
    ls <- layout_summary(ppt)
    while (length(ppt) < 5) ppt <- add_slide(ppt, layout = ls$layout[1], master = ls$master[1])
  }
  
  ppt <- on_slide(ppt, index = 3) %>% 
    ph_with(value = ft_pp, location = ph_location(left = 0.32, top = 1.05, width = 9.35, height = 3.55))
    
  ppt <- on_slide(ppt, index = 4) %>% 
    ph_with(value = ft_pm, location = ph_location(left = 0.32, top = 1.05, width = 9.35, height = 3.55))



    # Repartition notation et taux de complétude des agents par intervalle de taux


    notation=read.csv(paste0(chemin,"notation.csv"), header = FALSE, row.names = NULL)

    colnames(notation)=c("Agent","Filiale","Note","Date_notation")
    
    filiale_note=unique(notation$Filiale)


notation= notation  %>%
    group_by(Filiale, Note) %>%
    summarise(Count = n(), .groups = "drop") %>%
    group_by(Filiale) %>%
    mutate(Nombre_notes = sum(Count)) %>%
    mutate(Percent = Count / Nombre_notes) %>%    # proportion (0 à 1)
    mutate(Percent = percent(Percent, accuracy = 0.2)) %>%  # transforme en “xx.x%”
    select(Filiale, Nombre_notes, Note, Percent) %>%
    pivot_wider(names_from = Note, values_from = Percent, values_fill = "0%")


    


          note_cols <- c("Insuffisant", "Passable", "Bien", "Très Bien")
          for (col in note_cols) {
            if (!(col %in% colnames(notation))) notation[[col]] <- "0%"
          }

          notation_fil=notation[notation$Filiale==paste0("BOA ",fil),]
          if (nrow(notation_fil) == 0) {
            notation_fil <- data.frame(
              Filiale = paste0("BOA ", fil),
              Nombre_notes = 0,
              Insuffisant = "0%",
              Passable = "0%",
              Bien = "0%",
              "Très Bien" = "0%",
              check.names = FALSE
            )
          } else {
            notation_fil <- notation_fil[, c("Filiale", "Nombre_notes", note_cols), drop = FALSE]
          }
          colnames(notation_fil)=c("Filiale","Nombre notes","Insuffisant","Passable","Bien","Très Bien")

          repartition_pp <- agent_distribution_row(agent_completion_rates(pp_ne, pp_fields))
          repartition_pm <- agent_distribution_row(agent_completion_rates(pm_ne, pm_fields))
          taux_compl <- as.data.frame(rbind(repartition_pp, repartition_pm), check.names = FALSE)
          taux_compl <- data.frame(
            Taux = c("Taux stock PP", "Taux stock PM"),
            taux_compl,
            check.names = FALSE
          )

          ft_taux_compl <- style_slide5_table(taux_compl, widths = c(2.5, 1.35, 1.35, 1.35, 1.35))
          ft_notation <- style_slide5_table(notation_fil, widths = c(1.45, 1.35, 1.3, 1.3, 1.3, 1.3))

          ppt <- on_slide(ppt, index = 5) %>%
            ph_with(value = ft_taux_compl, location = ph_location(left = 0.75, top = 1.45, width = 7.9, height = 0.75)) %>%
            ph_with(value = ft_notation, location = ph_location(left = 0.75, top = 3.35, width = 8.0, height = 0.65))


# Nombbre de clients non fiabilisés


    non_fiab=read.csv2(paste(sep="",chemin,fil,"//data//non_fiab.csv"), fileEncoding = "UTF-8-BOM") %>% clean_colnames()
  pm_ne$AGENCE <- as.numeric(pm_ne$AGENCE)
  

    non_fiab=non_fiab[non_fiab$CODE=="OI",]

                par_5= fpar(ftext(paste0("Les comptes faisant objet d'interdit crédit et débit ne sont pas intégrés dans les comptes à fiabiliser et sont au nombre de ",nrow((non_fiab))), fp_text(color = "black",font.size = 14, font.family="Times New Roman")))
                ppt <- on_slide(ppt, index = 5) %>%
                  ph_with(value = par_5, location = ph_location(left = 0.75, top = 4.15, width = 8.0, height = 0.75))




   print(ppt,target=paste(chemin,fil,"//Rapport fiabilisation KYC BOA ",fil," _ V2 ",format(Sys.Date(),"%B %Y"),".pptx",sep=""))

  cat("PPT généré avec succès pour", fil, "\n")
}
