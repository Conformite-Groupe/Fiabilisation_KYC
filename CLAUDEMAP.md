# CLAUDEMAP — Fiabilisation KYC v3.0
> Carte de navigation du projet. Mise à jour : 2026-06-25.
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
| `kyc/models.py` | Modèles : `KYC_PP`, `KYC_PM`, `DateRev`, `DataQualityRule`, `DataQualityCondition`, `KYCDocumentExtraction`, `KYCDocumentMatchSettings`, `KYCCompletenessFieldConfig`, `KYCFieldVisibilityConfig`, `FilialeModuleConfig`, `KYCDocumentType`, `KYCExpiredDocumentScanMatch`, `KYCDocumentMatchJob` |
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

---

## Conventions & patterns importants

- **Filtrage par filiale** : les utilisateurs voient uniquement les données de leur(s) filiale(s) — vérifier `request.user` et `FilialeModuleConfig` avant toute vue.
- **Templates Tailwind** : la plupart des templates utilisent les classes Tailwind générées par `django-tailwind`. Rebuild nécessaire après modification des classes : `python manage.py tailwind build`.
- **Login** : URL `/login_kyc/` → vue `accounts.views.login_kyc` → template `accounts/templates/accounts/login_kyc.html`.
- **Exports** : les exports CSV/Excel passent par `kyc/pilotage_exports.py` et les vues `export_*` dans `kyc/views.py`.
- **Cache** : FileBasedCache dans `.django_cache/`, configuré dans `settings.py` via `.env`.
- **Fichiers secours** : `views_secours190925.py`, `base_secour190925.html`, `settings_secours.py` — ne pas supprimer, servent de rollback.

---

## Dernières modifications connues (2026-06-25)
- `accounts/templates/accounts/login_kyc.html` : redesign complet v3.0 (split-screen, floating KPI cards, toggle password, badges sécurité)
