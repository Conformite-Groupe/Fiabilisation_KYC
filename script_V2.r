

#####-----------------------IMPORTATION DES LIBRAIRIES-------------###########
      
cat("###############################################\n")
cat("######### FIABILISATION DES DONNEES KYC \n")
cat("######### ETAPE 1/3: CHAMPS A FIABILISER\n")
cat("##############################################\n")

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

#####-----------------------####-------------###########
chemin="C://Users//mamsylla//OneDrive - BANK OF AFRICA (1)//data//"

#####-----------------------####-------------###########

#####--------------DATES ( à modifier en prod) ------###########
#
   # premier_jour_mois_courant <- floor_date(Sys.Date(), "month")
   # premier_jour_mois_precedent <- premier_jour_mois_courant %m-% months(1)

  premier_jour_mois_courant <- "2026-03-01" 
  premier_jour_mois_precedent <- "2026-02-01"

  date_limite <- as.Date("2024/10/01") %m-% months(3)



#####-----------------------####-------------###########

prerequis=read.csv2(paste(sep="",chemin,"prerequis.csv"),header=F)


colnames(prerequis)=c("infos","argument","LIB_ETUDIANT","LIB_MINEUR")


filiale=prerequis$infos[prerequis$argument=="y"]


trimestre_actuel=as.character(prerequis[1,2])


inc=c("")



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


is_alphanumeric <- function(x) {
    grepl("[a-zA-Z]", x) | grepl("[0-9]", x)
}


remove_spaces <- function(x) {
  if (is.character(x)) {
    return(trimws(gsub("\\t", "", x)))
  }
  return(x)
}

# Nettoyage des espaces (début/fin + multiples)
clean_spaces <- function(x) {
  x <- ifelse(is.na(x), "", as.character(x))
  x <- gsub("[ \t]+", " ", x)
  trimws(x)
}

# Nettoyage + marquage des valeurs "rep" par colonne (vectorise)
clean_and_mark_anomalies <- function(df, start_col = 4) {
  if (is.null(df) || ncol(df) < start_col) return(df)
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
  sum(df[, idx, drop = FALSE] == "", na.rm = TRUE)
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

  data.frame(Agents = agents, Taux_Completude = min_vals, stringsAsFactors = FALSE)
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
read_csv2_auto <- function(path, ...) {
  enc_guess <- detect_encoding(path)
  encodings <- unique(c(enc_guess, "UTF-8-BOM", "UTF-8", "Windows-1252", "Latin1"))
  last_warning <- NULL

  for (enc in encodings) {
    res <- tryCatch(
      withCallingHandlers(
        read.csv2(path, fileEncoding = enc, ...),
        warning = function(w) {
          msg <- conditionMessage(w)
          if (grepl("invalid input", msg, ignore.case = TRUE)) {
            last_warning <<- msg
            invokeRestart("muffleWarning")
            stop("invalid_input_warning")
          }
          if (grepl("incomplete final line", msg, ignore.case = TRUE)) {
            invokeRestart("muffleWarning")
          }
        }
      ),
      error = function(e) e
    )

    if (!inherits(res, "error")) {
      if (!identical(enc, enc_guess)) {
        message("Correction encodage: ", enc)
      }
      return(res)
    }
  }

  stop("Lecture impossible (encodage). Dernier avertissement: ", last_warning)
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


notation=read.csv(paste0(chemin,"notation.csv"))

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

pm_stock=read_csv2_auto(paste(sep="",chemin,fil,"//data//pm_stock.csv"),
                     stringsAsFactors = FALSE,
                     skipNul = TRUE)
    
    pm_stock <- clean_colnames(pm_stock)
                    
    pm_stock[pm_stock=="NA"]=""
    pm_stock[is.na(pm_stock)]=""

    pm_stock=as.data.frame(lapply(pm_stock, remove_spaces))


    pm_stock$DATOUV = dmy(pm_stock$DATOUV) 
    
    diff_s=setdiff(pm_stock$CLIENT, non_fiab$CLIENT)

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

  

    pm_stock_f= pm_stock %>%
                        filter(if_any(everything(), ~ is.na(.) | . == ""))


  

   pm_flux_f= pm_flux %>%
                        filter(if_any(everything(), ~ is.na(.) | trimws(.) == ""))


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



    
    pp_stock=read_csv2_auto(paste(sep="",chemin,fil,"//data//pp_stock.csv"),
                     stringsAsFactors = FALSE,
                     skipNul = TRUE)
    
    pp_stock <- clean_colnames(pp_stock)
    
    pp_stock[pp_stock=="NA"]=""
    pp_stock[is.na(pp_stock)]=""
    
    cli_nul=which(pp_stock$CLIENT=="")
    if (length(cli_nul)!=0) {
        pp_stock=pp_stock[-cli_nul,]
    } else {
        pp_stock=pp_stock
    }
    
     pp_stock=as.data.frame(lapply(pp_stock, remove_spaces))

    
    pp_stock$DATOUV = dmy(pp_stock$DATOUV)

    diff=setdiff(pp_stock$CLIENT, non_fiab$CLIENT)

    pp_stock= pp_stock[pp_stock$CLIENT %in% diff,]
    
    
    clients_devise_pp = which(pp_stock$DEVISE %in% devise_fil)

    pp_stock[clients_devise_pp,"DEVISE"]= ""


    pp_flux <- pp_stock %>%
    filter(
        DATOUV >= as.Date(premier_jour_mois_precedent),
        DATOUV < as.Date(premier_jour_mois_courant)
    )


 pp_stock_f= pp_stock %>%
                        filter(if_any(everything(), ~ is.na(.) | trimws(.) == ""))


  

   pp_flux_f= pp_flux %>%
                        filter(if_any(everything(), ~ is.na(.) | trimws(.) == ""))


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
      zipr(paste0(chemin,fil,"//Archives","//Archives ",fil," _ ",Sys.Date(),".zip"), repertoire)

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
                    | expl$TEL %in% inc  | is.na(expl$TEL)=="TRUE" | expl$ADRESSE %in% inc  | is.na(expl$ADRESSE) | expl$NUMID %in% inc  | is.na(expl$NUMID)=="TRUE" | expl$DATNAIS %in% inc  | is.na(expl$DATNAIS)=="TRUE" | expl$DATVALID %in% inc  | is.na(expl$DATVALID)=="TRUE" | expl$ORIGINE_REVENU %in% inc  | is.na(expl$ORIGINE_REVENU)=="TRUE"  ,]
            n_cons=length(unique(n_expl_s$CLIENT))  
            
                a=floor(100-nrow(expl[expl$PAYNAIS %in% inc  | is.na(expl$PAYNAIS=="TRUE"),])/nrow(expl)*100)
                b=floor(100-nrow(expl[expl$PROFESSION %in% inc  | is.na(expl$PROFESSION=="TRUE"),])/nrow(expl)*100)
                c=floor(100-nrow(expl[expl$SALAIRE %in% inc  | is.na(expl$SALAIRE=="TRUE"),])/nrow(expl)*100)
                d=floor(100-nrow(expl[expl$CODAPE %in% inc  | is.na(expl$CODAPE=="TRUE"),])/nrow(expl)*100)
                e=floor(100-nrow(expl[expl$TEL %in% inc  | is.na(expl$TEL=="TRUE"),])/nrow(expl)*100)
                f=floor(100-nrow(expl[expl$ADRESSE %in% inc  | is.na(expl$ADRESSE=="TRUE"),])/nrow(expl)*100)
                g=floor(100-nrow(expl[expl$NUMID %in% inc  | is.na(expl$NUMID=="TRUE"),])/nrow(expl)*100)
                h=floor(100-nrow(expl[expl$DATNAIS %in% inc | is.na(expl$DATNAIS)=="TRUE",])/nrow(expl)*100)        
                i=floor(100-nrow(expl[expl$DATVALID %in% inc | is.na(expl$DATVALID)=="TRUE",])/nrow(expl)*100)    
                j=floor(100-nrow(expl[expl$ORIGINE_REVENU %in% inc | is.na(expl$ORIGINE_REVENU)=="TRUE",])/nrow(expl)*100)    

                taux=min(a,b,c,d,e,f,g,h,i,j)

                taux_rat=trimestre-taux

                if (taux<Faible) {
                appreciation = "Faible"
                } else if (taux>=Faible & taux<Moyen) {
                appreciation = "Moyen"
                } else {
                appreciation = "Bon"
                }

                #if (taux_rat<0) {
                #taux_ratt= paste("En avance de + ",abs(taux_rat),"%", sep="")
                #} else {
                #taux_ratt= paste("En retard de ",taux_rat,"%", sep="")
                #}

                taux=paste(taux, sep = "", "%")
                lieu_naiss=paste(a,"%", sep="")
                profession=paste(b,"%",sep="")
                revenu=paste(c,"%",sep="")
                codape=paste(d,"%",sep="")
                tel=paste(e,"%",sep="")
                adresse=paste(f,"%",sep="")
                nin=paste(g,"%",sep="")
                datnais=paste(h,"%",sep="")
                datvalid=paste(i,"%",sep="")
                origine=paste(j,"%",sep="")


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
                expl$ORIGINE_REVENU %in% inc  | is.na(expl$ORIGINE_REVENU)=="TRUE" |
                expl$TEL %in% inc  | is.na(expl$TEL)=="TRUE" ,] 


             
            
            n_cons=length(unique(n_expl$CLIENT))

         
       
            
                    a=floor(100-nrow(expl[expl$CAPITAL=="" | is.na(expl$CAPITAL)=="TRUE",])/nrow(expl)*100)
                    b=floor(100-nrow(expl[expl$CA=="" | is.na(expl$CA)=="TRUE",])/nrow(expl)*100)
                    c=floor(100-nrow(expl[expl$RESULTAT=="" | is.na(expl$RESULTAT)=="TRUE",])/nrow(expl)*100)
                    d=floor(100-nrow(expl[expl$RCSNO=="" | is.na(expl$RCSNO=="TRUE"),])/nrow(expl)*100)
                    e=floor(100-nrow(expl[expl$CODAPE=="" | is.na(expl$CODAPE=="TRUE"),])/nrow(expl)*100)
                    f=floor(100-nrow(expl[expl$AGEC=="" | is.na(expl$AGEC=="TRUE"),])/nrow(expl)*100)
                    g=floor(100-nrow(expl[expl$ORIGINE_REVENU=="" | is.na(expl$ORIGINE_REVENU=="TRUE"),])/nrow(expl)*100)
                    h=floor(100-nrow(expl[expl$TEL=="" | is.na(expl$TEL=="TRUE"),])/nrow(expl)*100)

                    taux=min(a,b,c,d,e,f,g,h)

                    taux_rat=trimestre-taux

                    if (taux<Faible) {
                    appreciation = "Faible"
                    } else if (taux>=Faible & taux<Moyen) {
                    appreciation = "Moyen"
                    } else {
                    appreciation = "Bon"
                    }

                    if (taux_rat<0) {
                    taux_ratt= paste("En avance de + ",abs(taux_rat),"%", sep="")
                    } else {
                    taux_ratt= paste("En retard de ",taux_rat,"%", sep="")
                    }

                    taux=paste(taux, sep = "", "%")
                    capital=paste(a,"%", sep="")
                    ca=paste(b,"%",sep="")
                    resultat=paste(c,"%",sep="")
                    rcsno=paste(d,"%",sep="")
                    codape=paste(e,"%",sep="")

                    agec=paste(f,"%",sep="")
                    origine=paste(g,"%",sep="")
                    tel=paste(h,"%",sep="")

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
          
            pp_ne=read.csv2(paste(sep="",chemin,fil,"//data//pp_",fil,".csv"), fileEncoding = "UTF-8-BOM")
            pp_ne <- clean_colnames(pp_ne)
            pp_ne$AGENCE=as.numeric(pp_ne$AGENCE)

            
            pp_ne=pp_ne[,1:20]
            pp_ne=pp_ne[,-c(2,4,9)]

            colnames(pp_ne)=toupper(colnames(pp_ne))
            pm_ne=read.csv2(paste(sep="",chemin,fil,"//data//pm_",fil,".csv"), fileEncoding = "UTF-8-BOM")
            pm_ne <- clean_colnames(pm_ne)
            pm_ne$AGENCE=as.numeric(pm_ne$AGENCE)


            
            pm_ne=pm_ne[,1:17]
pm_ne=pm_ne[,-c(2,4,16)]

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
       
        a=floor(100-nrow(pp_ne[pp_ne$PAYNAIS %in% inc,])/nrow(pp_ne)*100)
        b=floor(100-nrow(pp_ne[pp_ne$PROFESSION %in% inc ,])/nrow(pp_ne)*100)
        c=floor(100-nrow(pp_ne[pp_ne$SALAIRE %in% inc ,])/nrow(pp_ne)*100)
        d=floor(100-nrow(pp_ne[pp_ne$CODAPE %in% inc ,])/nrow(pp_ne)*100)
        e=floor(100-nrow(pp_ne[pp_ne$TEL %in% inc ,])/nrow(pp_ne)*100)
        f=floor(100-nrow(pp_ne[pp_ne$ADRESSE %in% inc ,])/nrow(pp_ne)*100)
        g=floor(100-nrow(pp_ne[pp_ne$NUMID %in% inc ,])/nrow(pp_ne)*100)
        h=floor(100-nrow(pp_ne[is.na(pp_ne$DATNAIS)=="TRUE",])/nrow(pp_ne)*100)
        i=floor(100-nrow(pp_ne[is.na(pp_ne$DATVALID)=="TRUE",])/nrow(pp_ne)*100)
        j=floor(100-nrow(pp_ne[is.na(pp_ne$ORIGINE_REV)=="TRUE",])/nrow(pp_ne)*100)

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

       
       
        champs=c("PAYNAIS","PROFESSION","SALAIRE","NUMID","CODAPE","TEL","DATNAIS","ADRESSE","DATVALID","ORIGINE_REV")

        cv <- count_empty_fields(pp_ne, champs)

      taux=floor(100*(1-(cv/(T*nrow(pp_ne)))))

        taux_rat=floor(trimestre-taux)


        if (taux<Faible) {
            appreciation = "Faible"
            
        } else if (taux>=Faible & taux<Moyen) {
            appreciation = "Moyen"
        } else {
            appreciation = "Bon"
        }

        if (taux_rat<0) {
          taux_ratt= paste("En avance de + ",abs(taux_rat),"%", sep="")
        } else {
            taux_ratt= paste("En retard de ",taux_rat,"%", sep="")
        }

        taux=paste(taux,"%",sep="")

        lieu_naiss=paste(a,"%", sep="")
        profession=paste(b,"%",sep="")
        revenu=paste(c,"%",sep="")
        codape=paste(d,"%",sep="")
        tel=paste(e,"%",sep="")
        adresse=paste(f,"%",sep="")
        nin=paste(g,"%",sep="")
        datnais=paste(h,"%",sep="")
        datvalid=paste(i,"%",sep="")
        origine=paste(j,"%",sep="")



       
        etat_pp_nes=data.frame(`Lieu de Naissance` = lieu_naiss, Profession = profession,Codape=codape, Revenu = revenu, NIN = nin, TEL=tel, Adresse=adresse,DATNAIS=datnais,DATVALID=datvalid, ORIGINE_REV=origine, `Taux de fiabilisation` =taux, Appréciation=appreciation, `Taux à rattrapper` = taux_ratt)
            pp=etat_pp_nes[,c(ncol(etat_pp_nes),ncol(etat_pp_nes)-1,ncol(etat_pp_nes)-2)]
            pp_t=data.frame(A="",V="")
            
            colnames(pp_t)=c(paste(fil),"")
            pp_t[1,]=c("PM","PP")
            pp_t[2,2]=c(pp[1,c(3)])
            pp_t[3,2]=c(pp[1,c(2)])
            
            rownames(pp_t)=c("","Taux de fiabilisation","Appréciation")
            ## Statistique a l'échelle filiale (PM)
            

            
            a=floor(100-nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",])/nrow(pm_ne)*100)
            b=floor(100-nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",])/nrow(pm_ne)*100)
            c=floor(100-nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",])/nrow(pm_ne)*100)
            d=floor(100-nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),])/nrow(pm_ne)*100)
            e=floor(100-nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),])/nrow(pm_ne)*100)
            f=floor(100-nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC=="TRUE"),])/nrow(pm_ne)*100)
            g=floor(100-nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc| is.na(pm_ne$ORIGINE_REV=="TRUE"),])/nrow(pm_ne)*100)
            h=floor(100-nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL=="TRUE"),])/nrow(pm_ne)*100)

           
            K=length(c(a,b,c,d,e,f,g,h))

         #   taux=floor(100*(1-sum(nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC)=="TRUE",]), nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",]), nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",]),
         #
              #nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",]), nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),]),
         #
             # nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),]), nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc | is.na(pm_ne$ORIGINE_REV)=="TRUE",]), nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL)=="TRUE",]))/(K*nrow(pm_ne))))
#

        champs=c("CAPITAL","CA","RESULTAT","RCSNO","CODAPE","AGEC","ORIGINE_REV","TEL")

        cv <- count_empty_fields(pm_ne, champs)
        
           taux=floor(100*(1-(cv/(K*nrow(pm_ne)))))
            
            taux_rat=floor(trimestre-taux)
            
            if (taux<Faible) {
              appreciation = "Faible"
            } else if (taux>=Faible & taux<Moyen) {
              appreciation = "Moyen"
            } else {
              appreciation = "Bon"
            }
            if (taux_rat<0) {
              taux_ratt= paste("En avance de + ",abs(taux_rat),"%", sep="")
            } else {
              taux_ratt= paste(taux_rat,"%", sep="")
            }
            
            taux=paste(taux, sep = "", "%")
            capital=paste(a,"%", sep="")
            ca=paste(b,"%",sep="")
            resultat=paste(c,"%",sep="")
            rcsno=paste(d,"%",sep="")
            codape=paste(e,"%",sep="")
            agec=paste(f,"%",sep="")
            origine=paste(g,"%",sep="")
            tel=paste(h,"%",sep="")


            
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
            
            taux_filiale_t=do.call("rbind",taux_filiale)
            taux_filiale_t=taux_filiale_t[-which(taux_filiale_t$NIN==""),]
            
      
     
            ## PM
            
            agents_pm=unique(pm_ne$AGENCE)#("[[:alnum:]]", pm_ne$EXPL)=="TRUE"])
            #agents_null_pm=pm_ne[grepl("[[:alnum:]]", pm_ne$EXPL)=="FALSE",]
            
          
            
            etat_expl=data.frame(Agence="",`Nbre clients concernés`="", AGEC="", Capital="", CA = "", Resultat = "", RCSNO = "", CODAPE= "",  ORIGINE_REV=origine, TEL=tel,  `Taux de fiabilisation`="", Appréciation="")#,  `Taux à rattrapper`="")

            taux_filiale_pm = lapply(agents_pm,taux_function_pm)
            
            taux_filiale_pm=do.call("rbind",taux_filiale_pm)
            taux_filiale_pm=taux_filiale_pm[-which(taux_filiale_pm$RCSNO==""),]
            
         
               
            
            rm(pp_ne,pm_ne)
            
            
            ### LE stock
            
            cat("######################################################\n")
            cat("######### Chargement des données Stock de\n",sigle, "#######\n")
            cat("#####################################################\n")
            # Importatations des donnees

           pp_ne=read.csv2(paste(sep="",chemin,fil,"//data//pp_",fil,"_STOCK.csv"), fileEncoding = "UTF-8-BOM")
            pp_ne <- clean_colnames(pp_ne)
            pp_ne$AGENCE=as.numeric(pp_ne$AGENCE)


            

            pp_ne=pp_ne[,1:20]
pp_ne=pp_ne[,-c(2,4,9)]
 
            colnames(pp_ne)=toupper(colnames(pp_ne))
            pm_ne=read.csv2(paste(sep="",chemin,fil,"//data//pm_",fil,"_STOCK.csv"), fileEncoding = "UTF-8-BOM")
            pm_ne <- clean_colnames(pm_ne)
            pm_ne$AGENCE=as.numeric(pm_ne$AGENCE)

            
            pm_ne=pm_ne[,1:17]
pm_ne=pm_ne[,-c(2,4,16)]
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
            
        a=floor(100-nrow(pp_ne[pp_ne$PAYNAIS %in% inc,])/nrow(pp_ne)*100)
        b=floor(100-nrow(pp_ne[pp_ne$PROFESSION %in% inc ,])/nrow(pp_ne)*100)
        c=floor(100-nrow(pp_ne[pp_ne$SALAIRE %in% inc ,])/nrow(pp_ne)*100)
        d=floor(100-nrow(pp_ne[pp_ne$CODAPE %in% inc ,])/nrow(pp_ne)*100)
        e=floor(100-nrow(pp_ne[pp_ne$TEL %in% inc ,])/nrow(pp_ne)*100)
        f=floor(100-nrow(pp_ne[pp_ne$ADRESSE %in% inc ,])/nrow(pp_ne)*100)
        g=floor(100-nrow(pp_ne[pp_ne$NUMID %in% inc ,])/nrow(pp_ne)*100)
        h=floor(100-nrow(pp_ne[is.na(pp_ne$DATNAIS)=="TRUE",])/nrow(pp_ne)*100)
        i=floor(100-nrow(pp_ne[is.na(pp_ne$DATVALID)=="TRUE",])/nrow(pp_ne)*100)
        j=floor(100-nrow(pp_ne[is.na(pp_ne$ORIGINE_REV)=="TRUE",])/nrow(pp_ne)*100)

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

       
       
        champs=c("PAYNAIS","PROFESSION","SALAIRE","NUMID","CODAPE","TEL","DATNAIS","ADRESSE","DATVALID","ORIGINE_REV")

        cv <- count_empty_fields(pp_ne, champs)


      taux=floor(100*(1-(cv/(T*nrow(pp_ne)))))
        
        taux_rat=floor(trimestre-taux)


        if (taux<Faible) {
            appreciation = "Faible"
            
        } else if (taux>=Faible & taux<Moyen) {
            appreciation = "Moyen"
        } else {
            appreciation = "Bon"
        }

        if (taux_rat<0) {
          taux_ratt= paste("En avance de + ",abs(taux_rat),"%", sep="")
        } else {
            taux_ratt= paste("En retard de ",taux_rat,"%", sep="")
        }

        taux=paste(taux,"%",sep="")

        lieu_naiss=paste(a,"%", sep="")
        profession=paste(b,"%",sep="")
        revenu=paste(c,"%",sep="")
        codape=paste(d,"%",sep="")
        tel=paste(e,"%",sep="")
        adresse=paste(f,"%",sep="")
        nin=paste(g,"%",sep="")
        datnais=paste(h,"%",sep="")
        datvalid=paste(i,"%",sep="")
        origine=paste(j,"%",sep="")



        etat_pp_nes=data.frame(`Lieu de Naissance` = lieu_naiss, Profession = profession,Codape=codape, Revenu = revenu, NIN = nin, TEL=tel, Adresse=adresse,DATNAIS=datnais, DATVALID=datvalid,ORIGINE_REV=origine, `Taux de fiabilisation` =taux, Appréciation=appreciation, `Taux à rattrapper` = taux_ratt)
        pp=etat_pp_nes[,c(ncol(etat_pp_nes),ncol(etat_pp_nes)-1,ncol(etat_pp_nes)-2)]
        pp_t=data.frame(A="",V="")
            
            colnames(pp_t)=c(paste(fil),"")
            pp_t[1,]=c("PM","PP")
            pp_t[2,2]=c(pp[1,c(3)])
            pp_t[3,2]=c(pp[1,c(2)])
            
            rownames(pp_t)=c("","Taux de fiabilisation","Appréciation")
            
            ## Statistique a l'échelle filiale (PM)
                     
            a=floor(100-nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",])/nrow(pm_ne)*100)
            b=floor(100-nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",])/nrow(pm_ne)*100)
            c=floor(100-nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",])/nrow(pm_ne)*100)
            d=floor(100-nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),])/nrow(pm_ne)*100)
            e=floor(100-nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),])/nrow(pm_ne)*100)
            f=floor(100-nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC=="TRUE"),])/nrow(pm_ne)*100)
            g=floor(100-nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc| is.na(pm_ne$ORIGINE_REV=="TRUE"),])/nrow(pm_ne)*100)
            h=floor(100-nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL=="TRUE"),])/nrow(pm_ne)*100)

           
            K=length(c(a,b,c,d,e,f,g,h))

          #  taux=floor(100*(1-sum(nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC)=="TRUE",]), nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",]), nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",]),
          #    nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",]), nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),]),
          #    nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),]), nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc | is.na(pm_ne$ORIGINE_REV)=="TRUE",]), nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL)=="TRUE",]))/(K*nrow(pm_ne))))
#
                   champs=c("CAPITAL","CA","RESULTAT","RCSNO","CODAPE","AGEC","ORIGINE_REV","TEL")

        cv <- count_empty_fields(pm_ne, champs)

   taux=floor(100*(1-(cv/(K*nrow(pm_ne)))))
            taux_rat=floor(trimestre-taux)
            
            if (taux<Faible) {
              appreciation = "Faible"
            } else if (taux>=Faible & taux<Moyen) {
              appreciation = "Moyen"
            } else {
              appreciation = "Bon"
            }
            if (taux_rat<0) {
              taux_ratt= paste("En avance de + ",abs(taux_rat),"%", sep="")
            } else {
              taux_ratt= paste(taux_rat,"%", sep="")
            }
            
            taux=paste(taux, sep = "", "%")
            capital=paste(a,"%", sep="")
            ca=paste(b,"%",sep="")
            resultat=paste(c,"%",sep="")
            rcsno=paste(d,"%",sep="")
            codape=paste(e,"%",sep="")
            agec=paste(f,"%",sep="")
            origine=paste(g,"%",sep="")
            tel=paste(h,"%",sep="")


            
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

            taux_filiale_t_stock=do.call("rbind",taux_filiale)
            taux_filiale_t_stock=taux_filiale_t_stock[-which(taux_filiale_t_stock$NIN==""),]
  
            
            
   
            
            ## PM
            
            agents_pm=unique(pm_ne$AGENCE)#("[[:alnum:]]", pm_ne$EXPL)=="TRUE"])
            #agents_null_pm=pm_ne[grepl("[[:alnum:]]", pm_ne$EXPL)=="FALSE",]
            

            etat_expl=data.frame(Agence="", `Nbre clients concernés`="",AGEC="", Capital="", CA = "", Resultat = "", RCSNO = "",CODAPE= "", ORIGINE_REV="", TEL=tel,  `Taux de fiabilisation`="", Appréciation="")#,  `Taux à rattrapper`="")
            taux_filiale_pm_stock = lapply(agents_pm,taux_function_pm)
            
            taux_filiale_pm_stock=do.call("rbind",taux_filiale_pm_stock)
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

        # Importatations des donnees
        pp_ne=read.csv2(paste(sep="",chemin,fil,"//data//pp_",fil,".csv"), fileEncoding = "UTF-8-BOM")
        pp_ne <- clean_colnames(pp_ne)
        pp_ne$AGENCE=as.numeric(pp_ne$AGENCE)

        pp_ne=pp_ne[is.na(pp_ne$AGENCE)=="FALSE",]
        
        pp_ne=pp_ne[,1:20]
pp_ne=pp_ne[,-c(2,4,9)]
        colnames(pp_ne)=toupper(colnames(pp_ne))

pm_ne=read.csv2(paste(sep="",chemin,fil,"//data//pm_",fil,".csv"), fileEncoding = "UTF-8-BOM")
        pm_ne <- clean_colnames(pm_ne)
          pm_ne$AGENCE=as.numeric(pm_ne$AGENCE)

                pm_ne=pm_ne[is.na(pm_ne$AGENCE)=="FALSE",]

        
        pm_ne=pm_ne[,1:17]
pm_ne=pm_ne[,-c(2,4,16)]

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

     
        a=floor(100-nrow(pp_ne[pp_ne$PAYNAIS %in% inc,])/nrow(pp_ne)*100)
        b=floor(100-nrow(pp_ne[pp_ne$PROFESSION %in% inc ,])/nrow(pp_ne)*100)
        c=floor(100-nrow(pp_ne[pp_ne$SALAIRE %in% inc ,])/nrow(pp_ne)*100)
        d=floor(100-nrow(pp_ne[pp_ne$CODAPE %in% inc ,])/nrow(pp_ne)*100)
        e=floor(100-nrow(pp_ne[pp_ne$TEL %in% inc ,])/nrow(pp_ne)*100)
        f=floor(100-nrow(pp_ne[pp_ne$ADRESSE %in% inc ,])/nrow(pp_ne)*100)
        g=floor(100-nrow(pp_ne[pp_ne$NUMID %in% inc ,])/nrow(pp_ne)*100)
        h=floor(100-nrow(pp_ne[is.na(pp_ne$DATNAIS)=="TRUE",])/nrow(pp_ne)*100)
        i=floor(100-nrow(pp_ne[is.na(pp_ne$DATVALID)=="TRUE",])/nrow(pp_ne)*100)
        j=floor(100-nrow(pp_ne[is.na(pp_ne$ORIGINE_REV)=="TRUE",])/nrow(pp_ne)*100)

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

      
       
        champs=c("PAYNAIS","PROFESSION","SALAIRE","NUMID","CODAPE","TEL","DATNAIS","ADRESSE","DATVALID","ORIGINE_REV")

        cv <- count_empty_fields(pp_ne, champs)

      taux=floor(100*(1-(cv/(T*nrow(pp_ne)))))

        taux_rat=floor(trimestre-taux)


        if (taux<Faible) {
            appreciation = "Faible"
            
        } else if (taux>=Faible & taux<Moyen) {
            appreciation = "Moyen"
        } else {
            appreciation = "Bon"
        }

       # if (taux_rat<0) {
       #   taux_ratt= paste("En avance de + ",abs(taux_rat),"%", sep="")
       # } else {
       #     taux_ratt= paste("En retard de ",taux_rat,"%", sep="")
       # }

        taux=paste(taux,"%",sep="")

        lieu_naiss=paste(a,"%", sep="")
        profession=paste(b,"%",sep="")
        revenu=paste(c,"%",sep="")
        codape=paste(d,"%",sep="")
        tel=paste(e,"%",sep="")
        adresse=paste(f,"%",sep="")
        nin=paste(g,"%",sep="")
        datnais=paste(h,"%",sep="")
        datvalid=paste(i,"%",sep="")
        origine=paste(j,"%",sep="")

       
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


            a=floor(100-nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",])/nrow(pm_ne)*100)
            b=floor(100-nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",])/nrow(pm_ne)*100)
            c=floor(100-nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",])/nrow(pm_ne)*100)
            d=floor(100-nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),])/nrow(pm_ne)*100)
            e=floor(100-nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),])/nrow(pm_ne)*100)
            f=floor(100-nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC=="TRUE"),])/nrow(pm_ne)*100)
            g=floor(100-nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc| is.na(pm_ne$ORIGINE_REV=="TRUE"),])/nrow(pm_ne)*100)
            h=floor(100-nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL=="TRUE"),])/nrow(pm_ne)*100)

           
            K=length(c(a,b,c,d,e))

           # taux=floor(100*(1-sum(nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC)=="TRUE",]), nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",]), nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",]),
           #   nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",]), nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),]),
           #   nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),]), nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc | is.na(pm_ne$ORIGINE_REV)=="TRUE",]), nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL)=="TRUE",]))/(K*nrow(pm_ne))))
#
       champs=c("CAPITAL","CA","RESULTAT","RCSNO","CODAPE","AGEC","ORIGINE_REV","TEL")

        cv <- count_empty_fields(pm_ne, champs)
            
               taux=floor(100*(1-(cv/(K*nrow(pm_ne)))))
            taux_rat=floor(trimestre-taux)
            
            if (taux<Faible) {
              appreciation = "Faible"
            } else if (taux>=Faible & taux<Moyen) {
              appreciation = "Moyen"
            } else {
              appreciation = "Bon"
            }
         # if (taux_rat<0) {
         #   taux_ratt= paste("En avance de + ",abs(taux_rat),"%", sep="")
         # } else {
         #   taux_ratt= paste(taux_rat,"%", sep="")
         # }
            
            taux=paste(taux, sep = "", "%")
            capital=paste(a,"%", sep="")
            ca=paste(b,"%",sep="")
            resultat=paste(c,"%",sep="")
            rcsno=paste(d,"%",sep="")
            codape=paste(e,"%",sep="")
            agec=paste(f,"%",sep="")
            origine=paste(g,"%",sep="")
            tel=paste(h,"%",sep="")


            
            etat_pm_nes=data.frame(AGEC=agec,`Capital`=capital, CA = ca, Resultat = resultat, RCSNO = rcsno,CODAPE= codape,  ORIGINE_REV=origine, TEL=tel, `Taux de fiabilisation`=taux, Appréciation=appreciation)##`Taux à rattrapper`=taux_ratt)
            
        pm=etat_pm_nes[,c(ncol(etat_pm_nes),ncol(etat_pm_nes)-1,ncol(etat_pm_nes)-2)]

       pp_t[2,1]=c(pm[1,c(2)])
            pp_t[3,1]=c(pm[1,c(1)])

          } else {
                    pp_t=data.frame(MR=c("PM","100%","100%"),RM=c("PP","100%","Bon"))
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
        
        taux_filiale_t=do.call("rbind",taux_filiale)
        taux_filiale_t=taux_filiale_t[-which(taux_filiale_t$NIN==""),]
        

        taux_completude_pp = data.frame(Agents=taux_filiale_t$Agents, Taux=taux_filiale_t$Taux.de.fiabilisation, Date=Sys.Date(), flux_stock=rep("F", nrow(taux_filiale_t)), pp_pm=rep("P", nrow(taux_filiale_t)))




   



      # minimum = taux_filiale_t[,c(2:8)]
      # minimum_1=c()
      # for (i in 1:ncol (minimum)) {
      #     minimume = gsub("%","",minimum[,i])
      #     minimum_1=cbind(minimum_1, as.numeric(minimume))
      # }
      # minimum_2 = c(paste("BOA", fil),min(minimum_1[,1]),min(minimum_1[,2]),min(minimum_1[,3]),min(minimum_1[,4]),min(minimum_1[,5]),min(minimum_1[,6]),min(minimum_1[,7]))
      # minimum_pp = rbind(minimum_2,minimum_pp)



  ## ANomalies flux

          stock="n"



anom_pp= function(x) {

          expl=pp_ne[pp_ne$EXPL==x,]
          expl$DATNAIS=dmy(expl$DATNAIS)
          expl$DATOUV=dmy(expl$DATOUV)
          expl$DATVALID=dmy(expl$DATVALID)


          expl$'AGE'=difftime(Sys.Date(),expl$DATNAIS,units = "weeks") / 52.143
          expl$AGE=gsub(" week", "", expl$AGE)

          expl$ANOMALIE_AGE=""
          expl$AGE_EER=""

          expl$ANOMALIE_DATE_EER=""

          expl$AGE_CIN=""

          ##########

          expl$AGE_EER=difftime(expl$DATOUV,expl$DATNAIS,units = "weeks") / 52.143

          expl$AGE_EER=gsub(" week", "", expl$AGE_EER)
            expl$AGE_EER=floor(as.numeric( expl$AGE_EER))

          expl$'AGE_CIN'=difftime(Sys.Date(),expl$DATVALID,units = "weeks") / 52.143
          expl$AGE_CIN=gsub(" week", "", expl$AGE_CIN)

           expl$AGE_CIN=floor(as.numeric( expl$AGE_CIN))




          if (prerequis$LIB_MINEUR[prerequis$infos==fil]!="") {
              expl$ANOMALIE_AGE[expl$AGE>=21 & expl$PROFESSION ==prerequis$LIB_MINEUR[prerequis$infos==fil]]="ANOMALIE - Mineur de plus de 21 ans"
          }

          if (prerequis$LIB_ETUDIANT[prerequis$infos==fil]!="") {

             expl$ANOMALIE_AGE[expl$AGE>=30 & expl$PROFESSION == prerequis$LIB_ETUDIANT[prerequis$infos==fil]]="ANOMALIE - Etudiant de plus de 30 ans"

                }

          expl$ANOMALIE_DATE_EER[expl$AGE_EER<0]="ANOMALIE - Date EER antérieure à la date de naissance"

           expl$ANOMALIE_CIN[expl$AGE_CIN>0]="ANOMALIE - Document d'identité expiré"
           expl$ANOMALIE_CIN[expl$AGE_CIN<=0]=""


          colnames(anomalies_pp_t)=colnames(expl)

          anomalies_pp_t=rbind(expl,anomalies_pp_t)
  
     }          


        anomalies_pp_t=matrix(,ncol=23)
        anomalies_pp=lapply(agents,anom_pp)
        anomalies_pp=do.call("rbind",anomalies_pp)
        
        anomalies_pp=anomalies_pp[-which(is.na(anomalies_pp$CLIENT)=="TRUE" | anomalies_pp$CLIENT==''),]
        col_anom_risque=which(names(anomalies_pp) == "RISQUE")
        col_anom_datouv=which(names(anomalies_pp) == "DATOUV")
        anomalies_pp=anomalies_pp[,-c(col_anom_risque,col_anom_datouv)]
        anomalies_pp_t= anomalies_pp %>%
                        filter(if_any(everything(), ~ !is.na(.) & grepl("ANOMALIE", as.character(.), ignore.case = TRUE)))

    agence_flux=unique(anomalies_pp_t$AGENCE)
    cat("###############################################\n")
    cat("######### Début anomalie agent \n")
    cat("##############################################\n")
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
    anomalie_agent=data.frame(AGENT="",TAUX_NON_ANOMALIE="")
    anomalie_agent_t=lapply(agents_anom,function_anom_agent)
    anomalie_agent=do.call("rbind",anomalie_agent_t)
    anomalie_agent=anomalie_agent[!anomalie_agent$AGENT=="",]

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
           cat("#########Début du taux d'agence \n")
           cat("##############################################\n")


        if (nrow(anomalies_pp)!=0) {
            expl=anomalies_pp

            expl=expl[,-c(1:3)]
            expl_anomalies=as.matrix(expl)
            n_anorm_i= sum(grepl("ANOMALIE",expl_anomalies, ignore.case=T))
            l=ncol(expl)-6
            expl=expl[,c(1:l)]
            total=ncol(expl)*nrow(expl) - length(which(expl==""))
            taux_anomalie=floor(100*(1-n_anorm_i/total))      
            taux_anomalie=paste(taux_anomalie,"%",sep="")
            taux_anomalie_fil=data.frame(FLUX="",TAUX_NON_ANOMALIE=taux_anomalie)
            taux_anomalie_fil_flux=taux_anomalie_fil            

        writeData(wb_anom_agents,paste("Tx non anomalie BOA_",fil), x=taux_anomalie_fil_flux, startRow=1, startCol=1)
        addStyle(wb_anom_agents,paste("Tx non anomalie BOA_",fil), headerStyle, cols=1:ncol(taux_anomalie_fil_flux), rows=1)
         
        }
                  
           ## PM
        exploitant="agent"
        agents_pm=unique(pm_ne$EXPL[grepl("[[:alnum:]]", pm_ne$EXPL)=="TRUE"])
        agents_null_pm=pm_ne[grepl("[[:alnum:]]", pm_ne$EXPL)=="FALSE",]

        etat_expl=data.frame(Agents="",`Nbre clients concernés`="", AGEC="", Capital="", CA = "", Resultat = "", RCSNO = "",CODAPE= "", ORIGINE_REV="", TEL="", `Taux de fiabilisation`="", Appréciation="" )##`Taux à rattrapper`="")
        taux_filiale_pm = lapply(agents_pm,taux_function_pm)
        
        taux_filiale_pm=do.call("rbind",taux_filiale_pm)
        taux_filiale_pm=taux_filiale_pm[-which(taux_filiale_pm$RCSNO==""),]


        taux_completude_pm = data.frame(Agents=taux_filiale_pm$Agents, Taux=taux_filiale_pm$Taux.de.fiabilisation, Date=Sys.Date(), flux_stock=rep("F", nrow(taux_filiale_pm)), pp_pm=rep("M", nrow(taux_filiale_pm)))



          #### les taux d'appréciation


          

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

        note_finale=data.frame(Filiale=fil, Notation=note_filiale_fll, Date=ymd(Sys.Date()))
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
     
          pp_ne=read.csv2(paste(sep="",chemin,fil,"//data//pp_",fil,"_STOCK.csv"), fileEncoding = "UTF-8-BOM")
            pp_ne <- clean_colnames(pp_ne)
            pp_ne$AGENCE=as.numeric(pp_ne$AGENCE)

          #
          pp_ne=pp_ne[,1:20]
pp_ne=pp_ne[,-c(2,4,9)]
          colnames(pp_ne)=toupper(colnames(pp_ne))


          pm_ne=read.csv2(paste(sep="",chemin,fil,"//data//pm_",fil,"_STOCK.csv"), fileEncoding = "UTF-8-BOM")
            pm_ne <- clean_colnames(pm_ne)
            pm_ne$AGENCE=as.numeric(pm_ne$AGENCE)

          #
          pm_ne=pm_ne[,1:17]
pm_ne=pm_ne[,-c(2,4,16)]
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
        a=floor(100-nrow(pp_ne[pp_ne$PAYNAIS %in% inc,])/nrow(pp_ne)*100)
        b=floor(100-nrow(pp_ne[pp_ne$PROFESSION %in% inc ,])/nrow(pp_ne)*100)
        c=floor(100-nrow(pp_ne[pp_ne$SALAIRE %in% inc ,])/nrow(pp_ne)*100)
        d=floor(100-nrow(pp_ne[pp_ne$CODAPE %in% inc ,])/nrow(pp_ne)*100)
        e=floor(100-nrow(pp_ne[pp_ne$TEL %in% inc ,])/nrow(pp_ne)*100)
        f=floor(100-nrow(pp_ne[pp_ne$ADRESSE %in% inc ,])/nrow(pp_ne)*100)
        g=floor(100-nrow(pp_ne[pp_ne$NUMID %in% inc ,])/nrow(pp_ne)*100)
        h=floor(100-nrow(pp_ne[is.na(pp_ne$DATNAIS)=="TRUE",])/nrow(pp_ne)*100)
        i=floor(100-nrow(pp_ne[is.na(pp_ne$DATVALID)=="TRUE",])/nrow(pp_ne)*100)
        j=floor(100-nrow(pp_ne[is.na(pp_ne$ORIGINE_REV)=="TRUE",])/nrow(pp_ne)*100)

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
      
       
        champs=c("PAYNAIS","PROFESSION","SALAIRE","NUMID","CODAPE","TEL","DATNAIS","ADRESSE","DATVALID","ORIGINE_REV")

        cv <- count_empty_fields(pp_ne, champs)

      taux=floor(100*(1-(cv/(T*nrow(pp_ne)))))
        taux_rat=floor(trimestre-taux)


        if (taux<Faible) {
            appreciation = "Faible"
            
        } else if (taux>=Faible & taux<Moyen) {
            appreciation = "Moyen"
        } else {
            appreciation = "Bon"
        }

      # if (taux_rat<0) {
      #   taux_ratt= paste("En avance de + ",abs(taux_rat),"%", sep="")
      # } else {
      #     taux_ratt= paste("En retard de ",taux_rat,"%", sep="")
      # }

        taux=paste(taux,"%",sep="")

        lieu_naiss=paste(a,"%", sep="")
        profession=paste(b,"%",sep="")
        revenu=paste(c,"%",sep="")
        codape=paste(d,"%",sep="")
        tel=paste(e,"%",sep="")
        adresse=paste(f,"%",sep="")
        nin=paste(g,"%",sep="")
        datnais=paste(h,"%",sep="")
        datvalid=paste(i,"%",sep="")
        origine=paste(j,"%",sep="")



       
        etat_pp_nes=data.frame(`Lieu de Naissance` = lieu_naiss, Profession = profession,Codape=codape, Revenu = revenu, NIN = nin, TEL=tel, Adresse=adresse,DATNAIS=datnais,DATVALID=datvalid, ORIGINE_REV=origine, `Taux de fiabilisation` =taux, Appréciation=appreciation)##`Taux à rattrapper` = taux_ratt)
        pp=etat_pp_nes[,c(ncol(etat_pp_nes),ncol(etat_pp_nes)-1,ncol(etat_pp_nes)-2)]
        pp_t=data.frame(A="",V="")

        colnames(pp_t)=c(paste(fil),"")
        pp_t[1,]=c("PM","PP")
        pp_t[2,2]=c(pp[1,c(3)])
        pp_t[3,2]=c(pp[1,c(2)])

        rownames(pp_t)=c("","Taux de fiabilisation","Appréciation")

        ## Statistique a l'échelle filiale (PM)
            a=floor(100-nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",])/nrow(pm_ne)*100)
            b=floor(100-nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",])/nrow(pm_ne)*100)
            c=floor(100-nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",])/nrow(pm_ne)*100)
            d=floor(100-nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),])/nrow(pm_ne)*100)
            e=floor(100-nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),])/nrow(pm_ne)*100)
            f=floor(100-nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC=="TRUE"),])/nrow(pm_ne)*100)
            g=floor(100-nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc| is.na(pm_ne$ORIGINE_REV=="TRUE"),])/nrow(pm_ne)*100)
            h=floor(100-nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL=="TRUE"),])/nrow(pm_ne)*100)

           
            K=length(c(a,b,c,d,e))

           #taux=floor(100*(1-sum(nrow(pm_ne[pm_ne$AGEC %in% inc | is.na(pm_ne$AGEC)=="TRUE",]), nrow(pm_ne[pm_ne$CAPITAL %in% inc | is.na(pm_ne$CAPITAL)=="TRUE",]), nrow(pm_ne[pm_ne$CA %in% inc | is.na(pm_ne$CA)=="TRUE",]),
           #  nrow(pm_ne[pm_ne$RESULTAT %in% inc | is.na(pm_ne$RESULTAT)=="TRUE",]), nrow(pm_ne[pm_ne$RCSNO %in% inc | is.na(pm_ne$RCSNO=="TRUE"),]),
           #  nrow(pm_ne[pm_ne$CODAPE %in% inc | is.na(pm_ne$CODAPE=="TRUE"),]), nrow(pm_ne[pm_ne$ORIGINE_REV %in% inc | is.na(pm_ne$ORIGINE_REV)=="TRUE",]), nrow(pm_ne[pm_ne$TEL %in% inc | is.na(pm_ne$TEL)=="TRUE",]))/(K*nrow(pm_ne))))

                   champs=c("CAPITAL","CA","RESULTAT","RCSNO","CODAPE","AGEC","ORIGINE_REV","TEL")

        cv <- count_empty_fields(pm_ne, champs)
           taux=floor(100*(1-(cv/(K*nrow(pm_ne)))))

            taux_rat=floor(trimestre-taux)
            
            if (taux<Faible) {
              appreciation = "Faible"
            } else if (taux>=Faible & taux<Moyen) {
              appreciation = "Moyen"
            } else {
              appreciation = "Bon"
            }
          # if (taux_rat<0) {
          #   taux_ratt= paste("En avance de + ",abs(taux_rat),"%", sep="")
          # } else {
          #   taux_ratt= paste(taux_rat,"%", sep="")
          # }
            
            taux=paste(taux, sep = "", "%")
            capital=paste(a,"%", sep="")
            ca=paste(b,"%",sep="")
            resultat=paste(c,"%",sep="")
            rcsno=paste(d,"%",sep="")
            codape=paste(e,"%",sep="")
            agec=paste(f,"%",sep="")
            origine=paste(g,"%",sep="")
            tel=paste(h,"%",sep="")
            
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

        taux_filiale_t_stock=do.call("rbind",taux_filiale)
        taux_filiale_t_stock=taux_filiale_t_stock[-which(taux_filiale_t_stock$NIN==""),]

        taux_completude_stock_pp = data.frame(Agents=taux_filiale_t_stock$Agents, Taux=taux_filiale_t_stock$Taux.de.fiabilisation, Date=rep(Sys.Date(),nrow(taux_filiale_t_stock)), flux_stock=rep("S", nrow(taux_filiale_t_stock)), pp_pm=rep("P", nrow(taux_filiale_t_stock)))


        ########## Anomalies par agent
               
        anomalies_pp_t=matrix(,ncol=23)
        anomalies_pp=lapply(agents,anom_pp)

        anomalies_pp=do.call("rbind",anomalies_pp)
        anomalies_pp=anomalies_pp[-which(is.na(anomalies_pp$CLIENT)=="TRUE"),]


      # Les agents avec les clients en anomalie
        anomalies_pp_t= anomalies_pp %>%
                        filter(if_any(everything(), ~ !is.na(.) & grepl("ANOMALIE", as.character(.), fixed = TRUE)))

        les_anomalies=data.frame(AGENCE=anomalies_pp_t$AGENCE, EXPL=anomalies_pp_t$EXPL, CLIENT=anomalies_pp_t$CLIENT, CODAPE=anomalies_pp_t$CODAPE, 
                                 IDP=anomalies_pp_t$IDP, ANOMALIE_AGE=anomalies_pp_t$ANOMALIE_AGE, ANOMALIE_DATE_EER=anomalies_pp_t$ANOMALIE_DATE_EER, ANOMALIE_CIN=anomalies_pp_t$ANOMALIE_CIN)

readr::write_excel_csv2(les_anomalies, paste0(chemin, fil, "//data//anomalies_", fil, ".csv"))

        #anomalies_pp_t=data.frame(AGENCE=anomalies_pp$AGENCE, EXPL=anomalies_pp$EXPL, CLIENT=anomalies_pp$CLIENT, DATNAIS=anomalies_pp$DATNAIS,DATE_EER=anomalies_pp$DATOUV,PROFESSION=anomalies_pp$PROFESSION,AGE=anomalies_pp$AGE,
         #                 ANOMALIE_AGE=anomalies_pp$ANOMALIE_AGE,AGE_EER=anomalies_pp$AGE_EER,ANOMALIE_DATE_EER=anomalies_pp$ANOMALIE_DATE_EER,DATVALID_CIN=anomalies_pp$DATVALID,ANOMALIE_CIN=anomalies_pp$ANOMALIE_CIN)

        agence_stock=unique(anomalies_pp_t$AGENCE)


        agents_anom=unique(anomalies_pp_t$EXPL)
        anomalie_agent=data.frame(AGENT="",TAUX_NON_ANOMALIE="")

        anomalie_agent_t=lapply(agents_anom,function_anom_agent)

        anomalie_agent=do.call("rbind",anomalie_agent_t)

        anomalie_agent=anomalie_agent[!anomalie_agent$AGENT=="",]

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
          
         
                        expl=anomalies_pp

                        expl=expl[,-c(1:3)]

                        expl_anomalies=as.matrix(expl)
                        n_anorm_i= sum(grepl("ANOMALIE",expl_anomalies, ignore.case=T))

                        l=ncol(expl)-6
                        expl=expl[,c(1:l)]

                        total=ncol(expl)*nrow(expl) - length(which(expl==""))
                        taux_anomalie=floor(100*(1-n_anorm_i/total))

                                
                        taux_anomalie=paste(taux_anomalie,"%",sep="")

                         
                     

                         taux_anomalie_fil=data.frame(STOCK="",TAUX_NON_ANOMALIE=taux_anomalie)
                         taux_anomalie_fil_stock=taux_anomalie_fil

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
        
        taux_filiale_pm_stock=do.call("rbind",taux_filiale_pm_stock)
        taux_filiale_pm_stock=taux_filiale_pm_stock[-which(taux_filiale_pm_stock$RCSNO==""),]
      

      
        taux_completude_stock_pm = data.frame(Agents=taux_filiale_pm_stock$Agents, Taux=taux_filiale_pm_stock$Taux.de.fiabilisation, Date=Sys.Date(), flux_stock=rep("F", nrow(taux_filiale_pm_stock)), pp_pm=rep("M", nrow(taux_filiale_pm_stock)))





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

        note_finale=data.frame(Filiale=fil, Notation=note_filiale_fll, Date=Sys.Date())
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

          write.csv2(suivi_fiabilisation_out, paste0(chemin,fil,"//suivi_fiabilisation.txt"))
          
          write.csv2(suivi_fiabilisation_out, paste0(chemin,fil,"//data//suivi_fiabilisation_",fil,".csv"), row.names=FALSE)


          

          if (ncol(suivi_fiabilisation) > 1) {
            cols_sf <- seq_len(ncol(suivi_fiabilisation) - 1)
            suivi_fiabilisation[cols_sf] <- lapply(
              suivi_fiabilisation[cols_sf],
              function(x) as.numeric(gsub("%", "", x))
            )
          }

          suivi_fiabilisation$Date <- as.Date(suivi_fiabilisation$Date)


          suivi_fiabilisation <- suivi_fiabilisation[order(suivi_fiabilisation$Date), ]
    
          colnames(suivi_fiabilisation)=c("Flux_PM","Flux_PP","Stock_PM", "Stock_PP","Date")
     


          # Tracer le graphique avec les courbes et les valeurs
     # Tracer le graphique avec les courbes et les valeurs



 courbe_f <- ggplot(suivi_fiabilisation, aes(x = Date)) +
  
  # première courbe : Flux_PM
  geom_line(aes(y = Flux_PM, color = "Flux_PM"), linewidth = 1.2) +
  geom_point(aes(y = Flux_PM, color = "Flux_PM"), size = 3) +
  geom_text(aes(y = Flux_PM, label = paste0(Flux_PM, "%"), color = "Flux_PM"),
            vjust = -0.5, size = 5, check_overlap = TRUE) +
  
  # deuxième courbe : Flux_PP
  geom_line(aes(y = Flux_PP, color = "Flux_PP"), linewidth = 1.2) +
  geom_point(aes(y = Flux_PP, color = "Flux_PP"), size = 3) +
  geom_text(aes(y = Flux_PP, label = paste0(Flux_PP, "%"), color = "Flux_PP"),
            vjust = -0.5, size = 5, check_overlap = TRUE) +
  
  # formater l’axe des dates
  scale_x_date(date_labels = "%b %Y", date_breaks = "1 month") +
  
  # légendes et titres
  labs(
    x = "Date",
    y = "Pourcentage",
    color = "Légende"
  ) +
  
  # thèmes / style
  theme_minimal() +
  theme(
    plot.title = element_text(size = 16, face = "bold"),
    axis.title.x = element_text(size = 14),
    axis.title.y = element_text(size = 14),
    axis.text.x = element_text(size = 12, angle = 45, hjust = 1),
    axis.text.y = element_text(size = 12),
    legend.title = element_text(size = 14),
    legend.text = element_text(size = 12)
  )



            ## les graphiques Fiabilisation Stock

 courbef_f_pp <- ggplot(suivi_fiabilisation, aes(x = Date)) +

            # courbe : Stock_PM
            geom_line(aes(y = Stock_PM, color = "Stock_PM"), linewidth = 1.2) +
            geom_point(aes(y = Stock_PM, color = "Stock_PM"), size = 3) +
            geom_text(aes(y = Stock_PM, label = paste0(Stock_PM, "%"), color = "Stock_PM"),
                      vjust = -0.5, size = 5, check_overlap = TRUE) +

            # courbe : Stock_PP
            geom_line(aes(y = Stock_PP, color = "Stock_PP"), linewidth = 1.2) +
            geom_point(aes(y = Stock_PP, color = "Stock_PP"), size = 3) +
            geom_text(aes(y = Stock_PP, label = paste0(Stock_PP, "%"), color = "Stock_PP"),
                      vjust = -0.5, size = 5, check_overlap = TRUE) +

            # formater l’axe des dates
            scale_x_date(date_labels = "%b %Y", date_breaks = "1 month") +

            # légendes et titres
            labs(
              x = "Date",
              y = "Pourcentage",
              color = "Légende"
            ) +

            # thèmes / style
            theme_minimal() +
            theme(
              plot.title = element_text(size = 16, face = "bold"),
              axis.title.x = element_text(size = 14),
              axis.title.y = element_text(size = 14),
              axis.text.x = element_text(size = 12, angle = 45, hjust = 1),
              axis.text.y = element_text(size = 12),
              legend.title = element_text(size = 14),
              legend.text = element_text(size = 12)
            )


# Sauvegarde des courbes
  ggsave(paste0(chemin,fil,"//temp_plot_f.png"), plot = courbe_f, width = 10, height = 8, units = "in")
  ggsave(paste0(chemin,fil,"//temp_plot.png"), plot = courbef_f_pp, width = 10, height = 8, units = "in")



  ## les graphiques Anomalies
  suivi_anomalie_i=as.data.frame(cbind(taux_anomalie_fil_flux[,2],taux_anomalie_fil_stock[,2],as.Date(premier_jour_mois_courant)-1))
  colnames(suivi_anomalie_i)=c("Flux PP","Stock PP","Date")
  suivi_anomalie_i$Date=as.Date(as.numeric(suivi_anomalie_i$Date))

  suivi_anomalie$Date=parse_date_any(suivi_anomalie$Date)
       
  colnames(suivi_anomalie)=c("Flux PP","Stock PP","Date")
  suivi_anomalie=rbind(suivi_anomalie,suivi_anomalie_i)


  suivi_anomalie_out <- suivi_anomalie
  suivi_anomalie_out$Date <- format(suivi_anomalie_out$Date, "%d/%m/%Y")
  write.csv2(suivi_anomalie_out, paste0(chemin,fil,"//suivi_anomalie.txt"))
  write.csv2(suivi_anomalie_out, paste0(chemin,fil,"//data//suivi_anomalie_",fil,".csv"), row.names=FALSE)


  colnames(suivi_anomalie)=c("Flux_PP","Stock_PP","Date")
  if (ncol(suivi_anomalie) > 1) {
    cols_sa <- seq_len(ncol(suivi_anomalie) - 1)
    suivi_anomalie[cols_sa] <- lapply(
      suivi_anomalie[cols_sa],
      function(x) floor(as.numeric(gsub("%", "", gsub(",", ".", x))))
    )
  }

            suivi_anomalie$Date <- as.Date(suivi_anomalie$Date)
          suivi_anomalie <- suivi_anomalie[order(suivi_anomalie$Date), ]


    


          # Tracer le graphique avec les courbes et les valeurs
courbef_a <- library(ggplot2)

library(ggplot2)
library(ggrepel) # Je te conseille vivement de garder ggrepel pour le fignolage

courbef_a <- ggplot(suivi_anomalie, aes(x = Date)) +
  
  # Courbe pour Flux_PP
  geom_line(aes(y = Flux_PP, color = "Flux_PP"), linewidth = 1.2) +
  geom_point(aes(y = Flux_PP, color = "Flux_PP"), size = 3) +
  geom_text_repel(aes(y = Flux_PP, label = paste0(format(Flux_PP, nsmall = 1), "%"), color = "Flux_PP"),
                  size = 5, nudge_y = 0.2) + 
  
  # Courbe pour Stock_PP
  geom_line(aes(y = Stock_PP, color = "Stock_PP"), linewidth = 1.2) +
  geom_point(aes(y = Stock_PP, color = "Stock_PP"), size = 3) +
  geom_text_repel(aes(y = Stock_PP, label = paste0(format(Stock_PP, nsmall = 1), "%"), color = "Stock_PP"),
                  size = 5, nudge_y = -0.2) + 
  
  # --- LA MODIFICATION ICI ---
  # On fixe les limites de 80 à 100 (ou plus si tes données montent plus haut)
  scale_y_continuous(limits = c(80, 100), breaks = seq(80, 100, by = 5)) +
  # ----------------------------

  scale_x_date(date_labels = "%b %Y", date_breaks = "1 month") +
  
  labs(
    x = "Date",
    y = "Pourcentage",
    color = "Légende"
  ) +
  
  theme_minimal() +
  theme(
    plot.title = element_text(size = 16, face = "bold"),
    axis.title.x = element_text(size = 14),
    axis.title.y = element_text(size = 14),
    axis.text.x = element_text(size = 12, angle = 45, hjust = 1),
    axis.text.y = element_text(size = 12),
    legend.title = element_text(size = 14),
    legend.text = element_text(size = 12),
    panel.grid.major = element_line(linewidth = 0.5)
  )

# Afficher le graphique
print(courbef_a)

ggsave(paste0(chemin,fil,"//temp_plot_anom.png"), plot = courbef_a, width = 10, height = 8, units = "in")

          l=ncol(tableau_suivi_t)
          tableau_fiabilisation_f=tableau_suivi_t
          colnames(tableau_fiabilisation_f)=c("Taux de complétude - Flux","-","--")
        
          tableau=flextable(tableau_fiabilisation_f)
          tableau=autofit(tableau,add_h=0,add_w=0)
          tableau=color(tableau,color="white", part="header")
          tableau=bg(tableau,bg=vert_fonce, part = "header")
          tableau=fontsize(tableau,size=10)
          tableau=fontsize(tableau,size=10,part="header")
          tableau= align(tableau, align = "center", part="header")
          tableau=theme_booktabs(tableau)

                
          tableau = merge_at(tableau, part="header", j = 1:3)

    # Champs critiques FLUX
          test=as.data.frame(lapply(taux_filiale_t, function(col) {as.numeric(gsub("%","",col))}))
          test_i=test[,-c(1,2,13,14)]

          test_i=as.data.frame(t(colMeans(test_i, na.rm=T)))

          cr=which((test_i[1,])<100)
         
          crit=as.data.frame(test_i[1,cr])

          colnames(crit)=colnames(test_i)[cr]
         
          crit[1,]=paste0(floor(crit[1,]),"%")
          crit_pp=cbind("Pourcentage", crit)
          colnames(crit_pp)[1]=c("(*)Champs critiques non renseignés - PP")
          
          
          crit_pp=flextable(crit_pp)
          crit_pp=autofit(crit_pp,add_h=0,add_w=0)
          crit_pp=color(crit_pp,color="white", part="header")
          crit_pp=bg(crit_pp,bg=vert_fonce, part = "header")
          crit_pp=fontsize(crit_pp,size=10)
          crit_pp=fontsize(crit_pp,size=10,part="header")
          crit_pp= align(crit_pp, align = "center", part="header")
          crit_pp=theme_booktabs(crit_pp)

           test_s=as.data.frame(lapply(taux_filiale_pm, function(col) {as.numeric(gsub("%","",col))}))
          test_i_s=test_s[,-c(1,2,11,12)]

          test_i_s=as.data.frame(t(colMeans(test_i_s, na.rm=T)))
          
          
          cr_s=which((test_i_s[1,])<100)

          crit_s=as.data.frame(test_i_s[1,cr_s])

          colnames(crit_s)=colnames(test_i_s)[cr_s]
         
          crit_s[1,]=paste0(floor(crit_s[1,]),"%")
          crit_pm=cbind("Pourcentage", crit_s)
          colnames(crit_pm)[1]=c("(*)Champs critiques non renseignés - PM")
          
          
          crit_pm=flextable(crit_pm)
          crit_pm=autofit(crit_pm,add_h=0,add_w=0)
          crit_pm=color(crit_pm,color="white", part="header")
          crit_pm=bg(crit_pm,bg=vert_fonce, part = "header")
          crit_pm=fontsize(crit_pm,size=10)
          crit_pm=fontsize(crit_pm,size=10,part="header")
          crit_pm= align(crit_pm, align = "center", part="header")
          crit_pm=theme_booktabs(crit_pm)

           ppt<-on_slide(ppt,3)
          loc_3=ph_location(left=2.5,top=1.3)
          loc_3a=ph_location(left=2.5,top=2.5)
          loc_3b=ph_location(left=2.5,top=3.3)



          loc_30=ph_location(left=0.4,top=1,width=1.8,height=0.3,bg=vert_fonce)
          par3= fpar(ftext(paste("Période: ",format(ymd(Sys.Date())-months(1), "%B %Y")), fp_text(color = "white",font.size = 10)))

          loc_30_a=ph_location(left=0.4,top=2.2,width=0.8,height=0.6,bg=bleu)
          par4= fpar(ftext(paste("FLUX"), fp_text(bold=TRUE,color = "black",font.size = 12)))


          ppt<-ph_with(ppt,par3,location=loc_30)
          ppt<-ph_with(ppt,par4,location=loc_30_a)


          ppt<-ph_with(ppt,tableau,location=loc_3)
          ppt<-ph_with(ppt,crit_pp,location=loc_3a)
          ppt<-ph_with(ppt,crit_pm,location=loc_3b)


          # Champs critiques Stock


          rm(test)
          rm(test_s)

          
          test=as.data.frame(lapply(taux_filiale_t_stock, function(col) {as.numeric(gsub("%","",col))}))
          test_i=test[,-c(1,2,13,14)]

          test_i=as.data.frame(t(colMeans(test_i, na.rm=T)))

          cr=which((test_i[1,])<90)
         
          crit=as.data.frame(test_i[1,cr])

          colnames(crit)=colnames(test_i)[cr]
         
          crit[1,]=paste0(floor(crit[1,]),"%")
          crit_pp=cbind("Pourcentage", crit)
          colnames(crit_pp)[1]=c("(**)Champs critiques non renseignés - PP")
          
          
          crit_pp=flextable(crit_pp)
          crit_pp=autofit(crit_pp,add_h=0,add_w=0)
          crit_pp=color(crit_pp,color="white", part="header")
          crit_pp=bg(crit_pp,bg=vert_fonce, part = "header")
          crit_pp=fontsize(crit_pp,size=10)
          crit_pp=fontsize(crit_pp,size=10,part="header")
          crit_pp= align(crit_pp, align = "center", part="header")
          crit_pp=theme_booktabs(crit_pp)

           test_s=as.data.frame(lapply(taux_filiale_pm_stock, function(col) {as.numeric(gsub("%","",col))}))
          test_i_s=test_s[,-c(1,2,11,12)]

          test_i_s=as.data.frame(t(colMeans(test_i_s, na.rm=T)))
          
          
          cr_s=which((test_i_s[1,])<90)

          crit_s=as.data.frame(test_i_s[1,cr_s])

          colnames(crit_s)=colnames(test_i_s)[cr_s]
         
          crit_s[1,]=paste0(floor(crit_s[1,]),"%")
          crit_pm=cbind("Pourcentage", crit_s)
          colnames(crit_pm)[1]=c("(**)Champs critiques non renseignés - PM")
          
          
          crit_pm=flextable(crit_pm)
          crit_pm=autofit(crit_pm,add_h=0,add_w=0)
          crit_pm=color(crit_pm,color="white", part="header")
          crit_pm=bg(crit_pm,bg=vert_fonce, part = "header")
          crit_pm=fontsize(crit_pm,size=10)
          crit_pm=fontsize(crit_pm,size=10,part="header")
          crit_pm= align(crit_pm, align = "center", part="header")
          crit_pm=theme_booktabs(crit_pm)


          ppt<-on_slide(ppt,3)
          loc_3a=ph_location(left=2.5,top=5.4)
          loc_3b=ph_location(left=2.5,top=6.2)

          ppt<-ph_with(ppt,crit_pp,location=loc_3a)
          ppt<-ph_with(ppt,crit_pm,location=loc_3b)
      

          rm(tableau)
          l=ncol(tableau_suivi_stock_t)
          tableau_fiabilisation_s=tableau_suivi_stock_t
          colnames(tableau_fiabilisation_s)=c("Taux de complétude - Stock","-","--")
          tableau=flextable(tableau_fiabilisation_s)
          tableau=autofit(tableau,add_h=0,add_w=0)
          tableau=color(tableau,color="white", part="header")
          tableau=bg(tableau,bg=vert_fonce, part = "header")
          tableau=fontsize(tableau,size=10)
          tableau=fontsize(tableau,size=10,part="header")
          tableau= align(tableau, align = "center", part="header")
          tableau=theme_booktabs(tableau)
          tableau = merge_at(tableau, part="header", j = 1:3)

          
          loc_31_a = ph_location(left=0.4,top=4.8,width=0.8,height=0.6,bg=bleu)
          par5= fpar(ftext(paste("STOCK"), fp_text(bold=TRUE,color = "black",font.size = 12)))

          
          loc_31=ph_location(left=2.5,top=4.3)

          ppt<-ph_with(ppt,tableau,location=loc_31)
          ppt<-ph_with(ppt,par5,location=loc_31_a)

        

        

     # Sauvegarder l'image avec des dimensions spécifiques
  
          loc_31=ph_location(left=7.8,top=1)
          ppt=ph_with(ppt, external_img(paste0(chemin,fil,"//temp_plot_f.png"), width = 10, height = 8), location = loc_31)

        
          loc_32=ph_location(left=7.8,top=4.3)
          ppt=ph_with(ppt, external_img(paste0(chemin,fil,"//temp_plot.png"), width = 10, height = 8), location = loc_32)


          taux_anomalie_fil_f=data.frame(FLUX=taux_anomalie_fil_flux[,2])
          colnames(taux_anomalie_fil_f)="TAUX NON ANOMALIE - FLUX"
          tableau=flextable(taux_anomalie_fil_f)
          tableau=autofit(tableau,add_h=0,add_w=0)
          tableau=color(tableau,color="white", part="header")
          tableau=bg(tableau,bg=vert_fonce, part = "header")
          tableau=fontsize(tableau,size=10)
          tableau=fontsize(tableau,size=10,part="header")
          tableau= align(tableau, align = "center")
          tableau=theme_booktabs(tableau)


          ppt<-on_slide(ppt,4)
          loc_4=ph_location(left=2,top=3)


          ppt<-ph_with(ppt,par3,location=loc_30)

          ppt<-ph_with(ppt,tableau,location=loc_4)
          ppt<-ph_with(ppt,par3,location=loc_30)


          taux_anomalie_fil_s=data.frame(STOCK=taux_anomalie_fil_stock[,2])
          colnames(taux_anomalie_fil_s)="TAUX NON ANOMALIE - STOCK"
          tableau=flextable(taux_anomalie_fil_s)
          tableau=autofit(tableau,add_h=0,add_w=0)
          tableau=color(tableau,color="white", part="header")
          tableau=bg(tableau,bg=vert_fonce, part = "header")
          tableau=fontsize(tableau,size=10)
          tableau=fontsize(tableau,size=10,part="header")
          tableau= align(tableau, align = "center")
          tableau=theme_booktabs(tableau)

         

          loc_41=ph_location(left=6,top=2)
          ppt=ph_with(ppt, external_img(paste0(chemin,fil,"//temp_plot_anom.png"), width = 10, height = 8), location = loc_41)
         


  
          loc_42=ph_location(left=2,top=4)
          ppt<-ph_with(ppt,tableau,location=loc_42)




          ppt<-on_slide(ppt,5)

           # Les statistiques sur les taux de fiabilisation par agents 


          agent_stock_pp=read_excel(paste0(chemin,fil,"//Rapport des taux de complétude par agent de BOA_",fil,".xlsx"), sheet=3)
          agent_stock_pm=read_excel(paste0(chemin,fil,"//Rapport des taux de complétude par agent de BOA_",fil,".xlsx"), sheet=4)


            breaks <- c(0, 50,60, 80, 100)

            ### Taux de complétude des agents PP
            inter_pp = as.numeric(gsub("%","", agent_stock_pp$Taux.de.fiabilisation))
                

            x_cut_pp <- cut(inter_pp, breaks = breaks, include.lowest = TRUE, right = TRUE,
                        labels = c("[0, 50%]", "]50% , 60%]","]60% , 80%]", "]80% , 100%]"))

                       
            t_fiabilisation=paste0(floor(100*(table(x_cut_pp)/length(x_cut_pp))),"%")

            labels = c("[0, 50%]", "]50% , 60%]","]60% , 80%]", "]80% , 100%]")

            fiab_pp=as.data.frame(rbind(labels,t_fiabilisation))
            colnames(fiab_pp)=fiab_pp[1,]
            fiab_pp=fiab_pp[-1,]
            rownames(fiab_pp)="Taux fiabilisation PP"




            ### Taux de complétude des agents PM

                   inter_pm = as.numeric(gsub("%","", agent_stock_pm$Taux.de.fiabilisation))
                

            x_cut_pm <- cut(inter_pm, breaks = breaks, include.lowest = TRUE, right = TRUE,
                        labels = c("[0, 50%]", "]50% , 60%]","]60% , 80%]", "]80% , 100%]"))

                       
            t_fiabilisation_pm=paste0(floor(100*(table(x_cut_pm)/length(x_cut_pm))),"%")

            labels = c("[0, 50%]", "]50% , 60%]","]60% , 80%]", "]80% , 100%]")

            fiab_pm=as.data.frame(rbind(labels,t_fiabilisation_pm))
            colnames(fiab_pm)=fiab_pm[1,]
            fiab_pm=fiab_pm[-1,]
            rownames(fiab_pm)="Taux fiabilisation PM"


           taux_compl=rbind(fiab_pp,fiab_pm)
            taux_compl=cbind(c("Taux fiabilisation PP","Taux fiabilisation PM"),taux_compl)
            colnames(taux_compl)[1]="Taux"
          
          
          rm(tableau)
          tableau=flextable(taux_compl)
          tableau=autofit(tableau,add_h=0,add_w=0)
          tableau=color(tableau,color="white", part="header")
          tableau=bg(tableau,bg=vert_fonce, part = "header")
          tableau=fontsize(tableau,size=10)
          tableau=fontsize(tableau,size=10,part="header")
          tableau= align(tableau, align = "center")
          tableau=theme_booktabs(tableau)

          loc_51=ph_location(left=0.5,top=1.85)

          ppt<-ph_with(ppt,tableau,location=loc_51)




         taux_anom=read_excel(paste0(chemin,fil,"//Taux de non-anomalie BOA_",fil,".xlsx"), sheet=5)


            breaks <- c(0, 50,60, 80, 100)

            ### Taux de complétude des agents PP
            anom_pp = as.numeric(gsub("%","", taux_anom$TAUX_NON_ANOMALIE))
                

            x_cut_pp_anom <- cut(anom_pp, breaks = breaks, include.lowest = TRUE, right = TRUE,
                        labels = c("[0, 50%]", "]50% , 60%]","]60% , 80%]", "]80% , 100%]"))

                       
            t_anom=paste0(floor(100*(table(x_cut_pp_anom)/length(x_cut_pp_anom))),"%")

            labels = c("[0, 50%]", "]50% , 60%]","]60% , 80%]", "]80% , 100%]")

            anom_pp=as.data.frame(rbind(labels,t_anom))
            colnames(anom_pp)=anom_pp[1,]
            anom_pp=anom_pp[-1,]
            rownames(anom_pp)="Taux non_anomalie PP"
            anom_pp=cbind(c("Taux nnon-anomalie PP"),anom_pp)

            colnames(anom_pp)[1]="Taux"



          rm(tableau)
          tableau=flextable(anom_pp)
          tableau=autofit(tableau,add_h=0,add_w=0)
          tableau=color(tableau,color="white", part="header")
          tableau=bg(tableau,bg=vert_fonce, part = "header")
          tableau=fontsize(tableau,size=10)
          tableau=fontsize(tableau,size=10,part="header")
          tableau= align(tableau, align = "center")
          tableau=theme_booktabs(tableau)

          loc_52=ph_location(left=0.5,top=3.9)

          ppt<-ph_with(ppt,tableau,location=loc_52)




          notation_fil=notation[notation$Filiale==paste0("BOA ",fil),]

          notation_fil=cbind(notation_fil$Filiale,notation_fil$Insuffisant,notation_fil$Passable,notation_fil$Bien,notation_fil$`Très Bien`)

          colnames(notation_fil)=c("Filiale","Insuffisant","Passable","Bien","Très Bien")
          notation_fil=as.data.frame((notation_fil))


          rm(tableau)
          tableau=flextable(notation_fil)
          tableau=autofit(tableau,add_h=0,add_w=0)
          tableau=color(tableau,color="white", part="header")
          tableau=bg(tableau,bg=vert_fonce, part = "header")
          tableau=fontsize(tableau,size=10)
          tableau=fontsize(tableau,size=10,part="header")
          tableau= align(tableau, align = "center")
          tableau=theme_booktabs(tableau)

          loc_53=ph_location(left=0.5,top=5.7)

          ppt<-ph_with(ppt,tableau,location=loc_53)



     


          par_5= fpar(ftext(paste0("Les comptes faisant objet d'interdit crédit et débit ne sont pas intégrés dans les comptes à fiabiliser et sont au nombre de ",nrow((non_fiab))), fp_text(color = "black",font.size = 14, font.family="Times New Roman")))
          loc_5=ph_location(left=1.5,top=6.5,width=11,height=1)

          ppt<-ph_with(ppt,par_5,location=loc_5)




          print(ppt,target=paste(chemin,fil,"//Rapport fiabilisation KYC BOA ",fil," _ ",format(Sys.Date(),"%B %Y"),".pptx",sep=""))


                dossier_a_supprimer <- paste0(chemin,fil,"//Anomalies par agence")

          unlink(dossier_a_supprimer, recursive = TRUE)


     ## Les taux de complétudepar agent flux et stock

          flux_pp=read_excel(paste0(chemin,fil,"//Rapport des taux de complétude par agent de BOA_",fil,".xlsx"), sheet=1)

          flux_pp=data.frame(Agents=flux_pp$Agents,Taux=flux_pp$Taux.de.fiabilisation,Date=rep(Sys.Date(),nrow(flux_pp)), flux_stock=rep("F",nrow(flux_pp)), pp_pm=rep("P",nrow(flux_pp)))

          flux_pm=read_excel(paste0(chemin,fil,"//Rapport des taux de complétude par agent de BOA_",fil,".xlsx"), sheet=2)
          flux_pm=data.frame(Agents=flux_pm$Agents,Taux=flux_pm$Taux.de.fiabilisation,Date=rep(Sys.Date(),nrow(flux_pm)), flux_stock=rep("F",nrow(flux_pm)), pp_pm=rep("M",nrow(flux_pm)))


          stock_pp=read_excel(paste0(chemin,fil,"//Rapport des taux de complétude par agent de BOA_",fil,".xlsx"), sheet=3)
          stock_pp=data.frame(Agents=stock_pp$Agents,Taux=stock_pp$Taux.de.fiabilisation,Date=rep(Sys.Date(),nrow(stock_pp)), flux_stock=rep("S",nrow(stock_pp)), pp_pm=rep("P",nrow(stock_pp)))

          stock_pm=read_excel(paste0(chemin,fil,"//Rapport des taux de complétude par agent de BOA_",fil,".xlsx"), sheet=4)
          stock_pm=data.frame(Agents=stock_pm$Agents,Taux=stock_pm$Taux.de.fiabilisation,Date=rep(Sys.Date(),nrow(stock_pm)), flux_stock=rep("S",nrow(stock_pm)), pp_pm=rep("M",nrow(stock_pm)))

          write.csv2(rbind(flux_pp,flux_pm,stock_pp,stock_pm), paste0(chemin,fil,"//data//taux_",fil,".csv"), row.names=FALSE)


          
      # Fichiers à archiver (sans chemins absolus)
      fichiers_a_archiver <- unique(zone$ZONE)
      
      repertoire=paste0(chemin,fil,"//",fichiers_a_archiver)


      repertoire <- repertoire[dir.exists(repertoire)]


      zipr(paste0(chemin,fil,"//Rapports Fiabilisation KYC BOA ",fil," _ ",format(Sys.Date() %m-% months(1), "%B %Y"),".zip"), repertoire)

     data_dir <- paste0(chemin, fil, "//data//")

fichiers_kyc <- c(
  paste0("anomalies_",fil,".csv"),
  paste0("taux_",fil,".csv"),
  paste0("suivi_fiabilisation_",fil,".csv"),
  paste0("suivi_anomalie_",fil,".csv"),
  paste0("scoring_",fil,".csv"),
  paste0("agents_",fil,".csv"),
  paste0("pp_",fil,"_STOCK_F.csv"),
  paste0("pm_",fil,"_STOCK_F.csv")
)

fichiers_kyc_exist <- fichiers_kyc[file.exists(file.path(data_dir, fichiers_kyc))]
zip_kyc <- paste0(data_dir, "KYC_", fil, "_", Sys.Date(), ".zip")

if (length(fichiers_kyc_exist) > 0) {
  if (file.exists(zip_kyc)) unlink(zip_kyc)
  zipr(zip_kyc, files = fichiers_kyc_exist, root = data_dir)
} else {
  message("Aucun fichier KYC a zipper dans: ", data_dir)
}



}



for (fil in filiale){
  tryCatch(
    production(fil),
    error = function(e) {
      message("Erreur filiale ", fil, " : ", e$message)
    }
  )
}


