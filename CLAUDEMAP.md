# CLAUDEMAP — Fiabilisation KYC v3.0
> Carte de navigation du projet. Mise à jour : 2026-06-25 (session 2).
> Objectif : permettre à Claude de localiser rapidement n'importe quelle partie du code sans exploration coûteuse.

---

## Stack technique
| Élément | Valeur |
|---|---|
| Framework | Django (Python 3.13) |
| CSS | Tailwind CSS via `django-tailwind` |
| JS | Alpine.js · Chart.js · html2pdf |
| DB | SQLite (dev) · config via `.env` |
| Auth | Django auth + modèle `User` standard + `UserLoginHistory` |
| Déploiement | HTTPS sur `kyc-test.of.africa` |
| Config env | `Fiabilisation_kyc/.env` (lu via `django-environ`) |

---

## Apps Django

### `kyc/` — App principale
| Fichier | Rôle |
|---|---|
| `kyc/models.py` | Modèles : `KYC_PP`, `KYC_PM`, `DateRev`, `DataQualityRule`, `DataQualityCondition`, `KYCDocumentExtraction`, `KYCDocumentMatchSettings`, `KYCCompletenessFieldConfig`, `KYCFieldVisibilityConfig`, `FilialeModuleConfig`, `KYCDocumentType`, `KYCExpiredDocumentScanMatch`, `KYCDocumentMatchJob`, `EmailReminderConfig`, **`KycDocumentOcrJob`** (file OCR), **`KycMatchValidatorRole`** (profils validateurs), **`KycMatchDecision`** (workflow validation), `TermTranslation` |
| `kyc/views.py` | Toutes les vues métier (≈ fichier principal, très volumineux) |
| `kyc/views_secours190925.py` | Vues de secours (backup 19/09/25, ne pas modifier) |
| `kyc/urls.py` | URLs préfixées `/trade/` |
| `kyc/forms.py` | Formulaires Django |
| `kyc/admin.py` | Configuration admin Django |
| `kyc/completeness.py` | Logique de calcul du taux de complétude KYC |
| `kyc/document_extraction.py` | Extraction et matching de documents d'identité |
| `kyc/context_processors.py` | Contexte global injecté dans tous les templates |
| `kyc/constants.py` | Constantes métier (champs PP/PM, choix, etc.) |
| `kyc/signals.py` | Signaux Django |
| `kyc/sec.py` | Utilitaires sécurité |
| `kyc/pilotage_exports.py` | Exports Excel/CSV pour le pilotage |
| `kyc/templatetags/custom_filters.py` | Filtres template personnalisés |
| `kyc/templatetags/extra_filters.py` | Filtres template additionnels |
| `kyc/templatetags/country_flag.py` | Tag drapeaux pays |

### `accounts/` — Authentification
| Fichier | Rôle |
|---|---|
| `accounts/models.py` | `UserLoginHistory` (historique connexions) |
| `accounts/views.py` | `login_kyc`, `logout_user`, `force_password_change` |
| `accounts/admin.py` | Admin comptes utilisateurs |
| `accounts/signals.py` | Signaux (post-login, etc.) |
| `accounts/validators.py` | Validateurs mot de passe |

### `Fiabilisation_kyc/` — Config Django
| Fichier | Rôle |
|---|---|
| `settings.py` | Settings principal (lit `.env`) |
| `settings_secours.py` | Settings de secours |
| `urls.py` | Router principal |
| `.env` | Secrets : `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, DB |

---

## URLs principales (`Fiabilisation_kyc/urls.py`)

| URL | Vue | Template |
|---|---|---|
| `/` | `accueil` | `accueil.html` |
| `/login_kyc/` | `login_kyc` | `accounts/login_kyc.html` ★ |
| `/perso/` | `perso` | `profil.html` |
| `/notation/` | `notes` | `notation.html` |
| `/non_rens/` | `non_rens` | `non_rens.html` |
| `/non_rens_pm/` | `non_rens_pm` | `non_rens_pm.html` |
| `/ppe/` | `ppe` | `ppe.html` |
| `/anom_ppe/` | `non_anom_ppe` | `anom_ppe.html` |
| `/devise/` | `devise` | `devise.html` |
| `/devise_pm/` | `devise_pm` | `devise_pm.html` |
| `/non_resid/` | `non_resid` | `non_resid.html` |
| `/non_resid_pm/` | `non_resid_pm` | `non_resid_pm.html` |
| `/scoring/` | `scoring` | `scoring.html` |
| `/clients_scorer/` | `clients_scorer` | `clients_scorer.html` |
| `/statistiques/` | `statistiques` | `statistiques.html` |
| `/evolution_filiale/` | `taux_evolution_view` | `evolution_par_filiale.html` |
| `/pilotage-kyc/` | `pilotage_kyc` | `pilotage_kyc.html` |
| `/daterev_ppe/` | `daterev_ppe` | `daterev_ppe.html` |
| `/document-extraction/` | `document_extraction` | `document_extraction.html` |
| `/quality-control/` (via `/trade/`) | — | `quality_control.html` |
| `/import/` | `import_page` | `import.html` |
| `/user_list/` | `user_list` | `user_list.html` |
| `/bulk-upload/` | `bulk_user_upload` | `bulk_upload.html` |
| `/kyc-field-config/` | `kyc_field_config` | `kyc_field_config.html` |
| `/daterev-reminder/` | `daterev_reminder` | `daterev_reminder.html` ★ |
| `/daterev-reminder/send/` | `send_daterev_reminders` | — (POST, redirect) |
| `/daterev-reminder/test-smtp/` | `test_smtp_config` | — (POST, redirect) |
| `/admin/` | Django admin | — |

---

## Templates

### Base layouts
| Template | Usage |
|---|---|
| `templates/base.html` | Layout principal actif (sidebar + navbar) |
| `templates/sidebar.html` | Sidebar (include dans base) |
| `templates/navbar.html` | Navbar (include dans base) |
| `templates/base_2412.html` | Layout alternatif (déc. 2024) |
| `templates/base_secour190925.html` | Layout de secours |

### Pages clés
| Template | Description |
|---|---|
| `accounts/templates/accounts/login_kyc.html` | **Page de login v3.0** (redesignée) — split-screen |
| `templates/dashboard.html` | Dashboard principal |
| `templates/accueil.html` | Page d'accueil post-login |
| `templates/quality_control.html` | Contrôle qualité des règles |
| `templates/document_extraction.html` | Extraction / matching documents |
| `templates/clients_scorer.html` | Scorer clients |
| `templates/pilotage_kyc.html` | Tableau de bord pilotage |
| `templates/completeness_admin.html` | Config complétude champs |
| `templates/kyc_field_config.html` | Visibilité des champs KYC |
| `templates/config_document_types.html` | Types de documents |
| `templates/includes/kpi_cards.html` | Composant KPI cards (include) |
| `templates/daterev_reminder.html` | **Page Rappels DATEREV** — entête glass-panel, KPI cards, tableau par filiale/exploitant, détail clients dépliable, modal test SMTP ★ |
| `templates/email_daterev_reminder.html` | **Email HTML** envoyé aux exploitants — tableau PP/PM, badges statut, branded BOA |

### Exports PDF
| Template | Description |
|---|---|
| `templates/quality_rules_pdf.html` | Export PDF règles qualité |
| `templates/quality_control_audits_pdf.html` | Export PDF audits |

---

## Scripts utilitaires (racine)

| Fichier | Usage |
|---|---|
| `import_kyc.py` | Import principal des données KYC |
| `import_premier.py` | Import premier chargement |
| `import_premier_mssql.py` | Import depuis MS SQL Server |
| `import_anomalies.py` | Import des anomalies |
| `import_taux_agent.py` | Import taux par agent |
| `create_users.py` | Création en masse d'utilisateurs |
| `modify_user.py` | Modification utilisateur |
| `delete_user.py` | Suppression utilisateur |
| `delete_table.py` | Vidage de table |
| `country_flag.py` | Utilitaire drapeaux (root) |
| `run_import_test.py` | Tests import |

---

## Static & assets

| Chemin | Contenu |
|---|---|
| `static/js/alpine.min.js` | Alpine.js (réactivité UI) |
| `static/js/chart.min.js` | Chart.js (graphiques) |
| `static/js/html2pdf.bundle.min.js` | Export PDF côté client |
| `static/js/custom.js` | JS personnalisé |
| `static/css/` | CSS compilé Tailwind |
| `media/images/boa.png` | Logo BOA (utilisé dans login + header) |
| `theme/static_src/tailwind.config.js` | Config Tailwind |

---

## Modèles clés (résumé)

### `KYC_PP` (Personnes Physiques)
Champs principaux : `FILIALE`, `AGENCE`, `CLIENT`, `CODAPE`, `IDP`, `PAYNAIS`, `PROFESSION`, `ADRESSE`, `PAYS_RESID`, `NUMID`, `SALAIRE`, `ORIGINE_REV`, `DATVALID`, `DATNAIS`, `TEL`, `DATOUV`, `PPE`, `DEVISE`, `RESID`, `DATEREV`

### `KYC_PM` (Personnes Morales)
Champs similaires adaptés aux entités morales.

### `DataQualityRule` + `DataQualityCondition`
Moteur de règles qualité configurable par filiale. Types : `simple` / `composite`. Opérateurs : `=`, `!=`, `>`, `<`, `contains`, `regex`, `is_empty`, `is_not_empty`, `expired`, `age_gt`, `age_lt`, `min_length`, `max_length`.

### `KYCDocumentExtraction`
Extraction OCR de documents d'identité avec matching fuzzy contre les données KYC.

### `FilialeModuleConfig`
Activation/désactivation des modules par filiale.

### Module Screening KYC ID (`/document-extraction/`)
Pipeline OCR + rapprochement documents ↔ clients KYC, en 4 phases :
- **Ingestion asynchrone** : upload rapide (hash SHA-256, dédup) → `KycDocumentOcrJob` traité par la commande `python manage.py process_document_ocr` (cron/loop). Statut par document : `pending/processing/done/failed`, relance OCR des échecs.
- **Lots multi-types** : type « Automatique (lot mixte) » → chaque fichier classé via `KycDocumentType` (mots-clés + apprentissage). Répartition par type, correction manuelle inline.
- **Rapprochement** : `_build_kyc_pp_document_matches` / `_build_kyc_pm_document_matches` dans `views.py`. Périmètre filiale, index par nom (`INTITULE_COMPTE`), poids configurables via `KycDocumentMatchSettings` (dates, lieu, nationalité, **nom & prénom**, seuils `combination_threshold` + `min_display_score`).
- **Validation** : `KycMatchDecision` (validé/rejeté/à valider, traçabilité qui/quand) ; profils autorisés = `KycMatchValidatorRole` (par organe, éditable en admin). Filtre de statut, rejetées masquées par défaut.
- Purge : `python manage.py purge_document_jobs --days 30`.
- ⚠️ `KycDocumentMatchSettings` : le nom/prénom est un **poids unique** (`fullname_weight`) comparé au champ `INTITULE_COMPTE` (nom+prénom regroupés) ; `CLIENT` est un numéro, pas un nom.

### `EmailReminderConfig`
Configuration SMTP + paramètres d'envoi pour les rappels DATEREV.
Champs : `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_use_tls`, `smtp_use_ssl`, `from_email`, `from_name`, `frequency` (manuel/quotidien/hebdo/mensuel), `days_before`, `active`.
Migration : `kyc/migrations/0037_emailreminderconfig.py`. Administrable via `/admin/kyc/emailreminderconfig/`.

---

## Conventions & patterns importants

- **Filtrage par filiale** : les utilisateurs voient uniquement les données de leur(s) filiale(s) — vérifier `request.user` et `FilialeModuleConfig` avant toute vue.
- **Templates Tailwind** : la plupart des templates utilisent les classes Tailwind générées par `django-tailwind`. Rebuild nécessaire après modification des classes : `python manage.py tailwind build`.
- **Login** : URL `/login_kyc/` → vue `accounts.views.login_kyc` → template `accounts/templates/accounts/login_kyc.html`.
- **Exports** : les exports CSV/Excel passent par `kyc/pilotage_exports.py` et les vues `export_*` dans `kyc/views.py`.
- **Cache** : FileBasedCache dans `.django_cache/`, configuré dans `settings.py` via `.env`. Clés toujours hashées MD5 (pas d'espaces ni caractères spéciaux) pour compatibilité memcached.
- **Préchauffage cache** : `python manage.py warm_ui_caches` — préchauffe quality, dashboards, specific, et **daterev** (toutes filiales). Options : `--users N`, `--rules N`, `--quality-only`, `--dashboards-only`, `--specific-only`.
- **Rappels DATEREV** : matching exploitant via `ProfileV.filiale` + `ProfileV.code_expl` (≠ `agence`). DATEREV est un CharField — parsing multi-format dans `_parse_daterev()`. Cache TTL 1h par `(filiale, date_today, days_before)`.
- **Fichiers secours** : `views_secours190925.py`, `base_secour190925.html`, `settings_secours.py` — ne pas supprimer, servent de rollback.

---

## Dernières modifications connues (2026-06-25)

### Session 1
- `accounts/templates/accounts/login_kyc.html` : redesign v3.0 — fond vert `#0a3d2e` plein écran, bloc connexion blanc centré, logo BOA en couleur, police `Plus Jakarta Sans`, chip version, toggle mot de passe
- `templates/base.html` (aside) : sidebar conserve le style blanc d'origine + icônes SVG sur chaque lien + animation hover (icône glisse à droite) + bouton déconnexion `mt-auto` en bas + active link `scrollIntoView()`

### Session 2 — Feature Rappels DATEREV
- `kyc/models.py` : ajout `EmailReminderConfig` (SMTP + fréquence)
- `kyc/migrations/0037_emailreminderconfig.py` : migration créée
- `kyc/admin.py` : `EmailReminderConfigAdmin` avec fieldsets SMTP / paramètres
- `kyc/views.py` : fonctions `_parse_daterev`, `_get_exploitants_daterev_expired`, vues `daterev_reminder`, `send_daterev_reminders`, `test_smtp_config` — matching exploitant via `ProfileV.code_expl` + cache MD5
- `Fiabilisation_kyc/urls.py` : 3 routes `/daterev-reminder/`, `/daterev-reminder/send/`, `/daterev-reminder/test-smtp/`
- `templates/base.html` : lien "Rappels DATEREV" dans section Administration (icône calendrier), visible pour `organe == PASS | DSI`
- `templates/daterev_reminder.html` : page admin — entête glass-panel style `evolution_filiale`, KPI cards (exploitants/clients/fenêtre), filtre filiale, tableau par filiale/exploitant, bouton envoi par exploitant/filiale/global, détail clients PP+PM dépliable, modal test SMTP, boutons `nav-link-active`
- `templates/email_daterev_reminder.html` : email HTML branded BOA — tableau clients avec badges statut
- `kyc/management/commands/warm_ui_caches.py` : ajout `_warm_daterev_reminders()` — préchauffe cache global + par filiale, clés MD5 safe
