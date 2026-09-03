# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Le code, les commentaires et l'UI sont en français. Garder cette langue dans les nouveaux ajouts.

## Commandes

Toujours passer par le venv du projet (`venv\Scripts\python.exe`) — les dépendances sont épinglées dans `requirements.txt`.

```bash
venv/Scripts/python.exe manage.py runserver
```

- Vérification statique : `python manage.py check`
- Tests : `python manage.py test kyc` — un seul test : `python manage.py test kyc.tests.KycDocumentTypeAutoLearningTest.test_document_classification_by_keywords`
  (`AXES_ENABLED` est désactivé automatiquement quand `sys.argv[1] == 'test'`)
- Migrations : `python manage.py makemigrations kyc && python manage.py migrate`
- CSS Tailwind v3 (obligatoire avant toute mise en prod, cf. `theme/static_src/package.json`) :
  `cd theme/static_src && npm run build`, puis `python manage.py collectstatic --noinput`, puis redémarrer Django.
  Dev : `python manage.py tailwind start`.
- Vider le cache : `python manage.py shell -c "from django.core.cache import cache; cache.clear()"`

### Traitements quotidiens

`app.txt` / `app_new.bat` (tâche planifiée Windows) enchaîne : redémarrage Django → `Script_V3.r` → `manage.py run_daily_jobs`.
`run_daily_jobs` est la commande unique qui orchestre la partie Django et envoie un rapport email de supervision :
worker OCR → `import_kyc.py` / `import_premier.py` / `import_taux_agent.py` → `compute_quality_rates`
→ `warm_ui_caches` → `compute_appreciation_globale` → rappels DATEREV.
Elle **ne lance plus `Script_V3.r`** (retiré le 21/08/2026) : le script R est exécuté en amont par `app.txt` étape 1
depuis `C:\Fiabilisation KYC\R`. `run_daily_jobs` se contente de relire le journal CSV qu'il produit
(`--r-journal`, défaut `logs/journal_script_v3.csv`) pour le détail par filiale du rapport.

Commandes utilisables isolément (`--skip ocr_worker,import_kyc,...` pour en désactiver une dans le batch) :

| Commande | Rôle |
|---|---|
| `compute_quality_rates` | Remplit `TauxQualite` (taux **stock** + **flux**) par scope ; `--prune-days` (400 j d'historique) |
| `warm_ui_caches --users 20 --rules 20` | Préchauffe les pages lourdes ; `--slice i/N` pour paralléliser (voir `scripts/warm_ui_caches_fast.ps1`) |
| `normalize_daterev` | Normalise `DATEREV` **et** `DATOUV` au format ISO — prérequis des calculs de dates |
| `process_document_ocr [--loop --interval 5 --workers 3]` | Worker OCR de la file Screening KYC ID |
| `purge_document_jobs --days 30` | Purge des jobs OCR/rapprochement |
| `compute_appreciation_globale`, `calculate_kyc_completeness`, `seed_glossary`, `seed_quality_rules_boa` | Voir `kyc/management/commands/` |

`generate_report.py --filiale SN [--json]` produit le PPTX d'audit d'une filiale à partir des CSV `pp_XX_STOCK.csv` / `pm_XX_STOCK.csv` et de `quality_rules_export.json`.

## Architecture

Django 5.2, `AUTH_USER_MODEL = accounts.ProfileV`, SQLite en dev (`db.sqlite3`), MSSQL (alias `prod`) en production.
Config via `django-environ`, fichier `Fiabilisation_kyc/.env` (pas le `.env` racine).
Cache : Redis si `CACHE_URL` est défini, sinon cache fichier `.django_cache`.

### Apps

- **`kyc/`** — cœur métier. `views.py` (~10 600 lignes) contient les dashboards, exports, moteur de règles qualité et écran Screening. Modules extraits : `completeness.py` (taux de complétude), `document_extraction.py` (OCR + détection de type de document), `pilotage_exports.py` (PDF/PPTX), `appreciation.py`, `daterev_mailer.py`, `audit_views.py`.
- **`accounts/`** — `ProfileV` (organe, filiale, agence, code_expl, `force_password_change`), `AuditEvent`, `UserLoginHistory`, login/verrouillage django-axes.
- **`kyc_audit/`** — pipeline d'audit hors-ligne (`dataset → completude/qualite/scoring → pipeline → deck`), lit des CSV, pas la base ; point d'entrée `generate_report.py`.
- **`theme/`** — app django-tailwind (Tailwind **v3**). Templates HTML dans `templates/` à la racine.

### Données KYC

`Kyc_pp` (particuliers, ~1,1 M lignes) et `Kyc_pm` (personnes morales) : **tous les champs sont des `CharField`**, y compris les dates (`DATEREV`, `DATOUV`, `DATNAIS`, `DATVALID`). Les comparaisons de dates sont donc **lexicales** → le format ISO est obligatoire (`normalize_daterev`). Index de scope : `FILIALE / AGENCE / EXPL`.

Chaîne d'alimentation : `Script_V3.r` (R, lit les exports filiales, gros CSV via `data.table::fread`) → CSV dans `KYC_DATA_DIR` → `import_kyc.py` (bulk, multiprocess) → tables Django.

### Périmètre (scope) et habilitations

Tout le contenu est filtré par le **scope effectif** de l'utilisateur, dérivé de son `organe` :
`_dashboard_effective_scope()` dans `kyc/views.py` renvoie `(role, filiale, agence, expl)` — `groupe` (organes groupe/zone/PASS), `filiale`, `agence` (Directeur Agence), `expl` (Chargé Client).

Trois couches d'habilitation :
- `SidebarAccess` (par organe) — visibilité des entrées de menu ; `perms_for(user)` retombe sur `legacy_perms_for_organe()` si aucune ligne n'existe.
- `KycScreeningAccess` (par organe) — onglets Screening KYC ID, chargement de lots, lancement du rapprochement.
- `FilialeModuleConfig` / `KycFieldVisibilityConfig` — modules et champs KYC activés par filiale.

### Cache des pages lourdes

Les dashboards sont mis en cache par `_build_dashboard_cache_key()` : hash de `(scope effectif, params GET whitelistés, version des données)`.
- La whitelist est `_DASHBOARD_QS_PARAMS` — **tout nouveau paramètre GET d'un dashboard doit y être ajouté**, sinon il est ignoré dans la clé et sert une page mise en cache pour une autre valeur.
- La version des données vient des dates max de `TauxEvolution*` + `quality_control_rules_version` : une injection matinale invalide automatiquement le cache.
- Les taux qualité affichés proviennent du snapshot précalculé `TauxQualite` (`_quality_rate_snapshot`), avec repli sur un calcul live si absent — jamais de rescan de `Kyc_pp` en ligne de mire.

### Règles qualité

`DataQualityRule` + `DataQualityCondition` (logique AND/OR) évaluées par `evaluate_data_quality_rule()` / `_evaluate_data_quality_rule_scoped()` dans `kyc/views.py` ; audits tracés dans `DataQualityRuleAudit`. Les règles sont exportables/importables (`export_rule.py` / `import_rule.py`, `quality_rules_export.json`).

### Screening KYC ID (extraction documentaire)

Upload (PDF/images/ZIP, validations de taille et de signature dans `views.py`) → `KycDocumentExtraction` → OCR asynchrone (`KycDocumentOcrJob`, worker `process_document_ocr`, moteur RapidOCR avec repli Tesseract) → rapprochement document ↔ client scoré (`_document_client_identity_score`, pondérations `KycDocumentMatchSettings`) exécuté en job (`KycDocumentMatchJob`) → validation humaine (`KycMatchDecision`, rôles `KycMatchValidatorRole`).
Les fichiers médias d'extraction ne sont **pas** servis en statique : ils passent par `serve_protected_media` qui vérifie le scope de l'utilisateur.

### Traduction FR/EN

Deux mécanismes cumulés : le filtre `|t` (`kyc/templatetags/extra_filters.py`) consulte d'abord le glossaire admin `TermTranslation` (cache 10 min) puis gettext. **Du texte brut dans un template n'est jamais traduit** — il faut le passer par `|t`. Le matching glossaire est exact : reprendre le `terme_fr` tel quel depuis le template (espaces insécables compris).

## Points d'attention

- `kyc/urls.py` (préfixe `/trade/`) redéclare plusieurs routes déjà présentes dans `Fiabilisation_kyc/urls.py` — la racine fait autorité pour la navigation.
- `warm_ui_caches` importe directement des vues et helpers privés de `kyc/views.py` : renommer un `_helper` ou changer une signature de vue casse la préchauffe.
- **Encodage des `organe`** : `SidebarAccess.organe` a déjà porté des doublons mojibake (« ConformitÃ© » à côté de « Conformité »), issus d'un import lu en cp1252. `perms_for()` résolvant d'abord la correspondance exacte, éditer la ligne mojibake dans l'admin n'avait aucun effet visible. Contrôle / correction : `python manage.py fix_sidebar_access_encoding --dry-run`.
- `SidebarAccess.perms_for()` renvoie **tout à True pour un superuser** : ne jamais valider une config de sidebar avec un compte `is_superuser`.
- Les `.pyc` sont versionnés dans ce dépôt ; ignorer leur bruit dans `git status`.
- Relais SMTP de prod : `mail.groupboa.com:25`, anonyme, autorisé par IP — ni TLS ni authentification.
