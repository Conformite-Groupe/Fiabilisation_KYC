# Rapport de scan de vulnerabilites - Plateforme Fiabilisation KYC

Date du scan: 2026-06-04  
Mode: audit statique et controles locaux, sans modification du code applicatif.

## Synthese

La plateforme presente plusieurs risques a corriger avant une mise en production ou une exposition reseau plus large.

Priorites:

1. Durcir la configuration Django (`DEBUG=False`, secret hors code, cookies securises, HTTPS/HSTS).
2. Revoir les vues sans authentification ou sans controle d'autorisation.
3. Supprimer les exemptions CSRF non justifiees.
4. Proteger les imports/exports KYC et les uploads de documents.
5. Nettoyer le depot Git des donnees sensibles et logs.
6. Aligner et mettre a jour les dependances Python.

## Critique

### 1. Secret Django en dur et DEBUG actif

Constats:

- `SECRET_KEY` est present en clair dans `Fiabilisation_kyc/settings.py`.
- La meme cle est presente dans `Fiabilisation_kyc/.env`.
- `DEBUG=True`.
- `ALLOWED_HOSTS` contient `0.0.0.0`.

Fichiers:

- `Fiabilisation_kyc/settings.py:46`
- `Fiabilisation_kyc/settings.py:49`
- `Fiabilisation_kyc/settings.py:50`
- `Fiabilisation_kyc/.env:1`
- `Fiabilisation_kyc/.env:2`
- `Fiabilisation_kyc/.env:3`

Risque:

- Exposition d'informations sensibles via pages d'erreur Django.
- Compromission potentielle des sessions/signatures si la cle a circule.
- Mauvais durcissement pour un environnement bancaire/KYC.

Corrections recommandees:

- Lire `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` depuis les variables d'environnement.
- Regenerer la `SECRET_KEY` avant production.
- Mettre `DEBUG=False` hors poste developpeur.
- Retirer `0.0.0.0` de `ALLOWED_HOSTS`.
- Ne jamais versionner `.env`.

Checklist:

- [ ] Regenerer `SECRET_KEY`.
- [ ] Mettre `DEBUG=False` en preproduction/production.
- [ ] Nettoyer `ALLOWED_HOSTS`.
- [ ] Verifier que `.env` n'est pas suivi par Git.
- [ ] Purger l'historique Git si le secret a ete pousse.

### 2. Vues sensibles sans protection suffisante

Constats:

Plusieurs vues sensibles sont exposees avec `csrf_exempt`, et certaines n'ont pas de `login_required`.

Exemples:

- `accounts/views.py:20` - `register`, creation utilisateur via GET et sans CSRF.
- `accounts/views.py:32` - `login_kyc`, login sans CSRF.
- `kyc/views.py:2850` - `profile`, modification profil sans `login_required`.
- `kyc/views.py:2877` - `reset_user_password_b`, reset mot de passe legacy sans `login_required`.
- `kyc/views.py:3119` - `notes`, notation sans `login_required`.
- `kyc/views.py:3159` - `agent_detail`, detail agent sans `login_required`.

Risque:

- Creation ou modification non autorisee.
- CSRF sur actions authentifiees.
- Fuite de donnees agents/KYC.
- Elevation de privileges selon les formulaires accessibles.

Corrections recommandees:

- Supprimer les `@csrf_exempt` sauf justification technique explicite.
- Ajouter `@login_required` sur toutes les vues metier.
- Ajouter des controles d'autorisation par `organe`, `filiale`, `agence`, `code_expl`.
- Desactiver ou supprimer les vues legacy non utilisees.

Checklist:

- [ ] Auditer toutes les occurrences `@csrf_exempt`.
- [ ] Ajouter `@login_required` aux vues metier.
- [ ] Ajouter des tests d'acces par role.
- [ ] Supprimer les endpoints legacy inutilises.

### 3. Donnees sensibles versionnees

Constats:

`git ls-files` montre que des fichiers metier et logs sont suivis par Git malgre `.gitignore`.

Exemples:

- `anomalies_BF.csv`
- `anomalies_CI.csv`
- `suivi_fiabilisation.csv`
- `suivi_fiabilisation_agent.csv`
- `logs/import_kyc.log`
- `logs/import_kyc.log.1`
- `logs/import_kyc.log.5`
- plusieurs fichiers sous `logs/import_runs/`

Risque:

- Exposition de donnees KYC, identifiants, dates de naissance, numeros d'identite, adresses et telephones.
- Non-conformite potentielle aux exigences de confidentialite et protection des donnees.

Corrections recommandees:

- Retirer ces fichiers du suivi Git avec `git rm --cached`.
- Garder les donnees locales hors depot.
- Mettre en place des exemples anonymises.
- Purger l'historique Git si le depot a ete partage.

Checklist:

- [ ] Retirer CSV/logs du suivi Git.
- [ ] Ajouter des fixtures anonymisees si necessaire.
- [ ] Purger l'historique si besoin.
- [ ] Revoir les droits d'acces au depot.

## Eleve

### 4. Exports KYC sans garde explicite uniforme

Constats:

Plusieurs fonctions d'export ou de consultation ne montrent pas de garde explicite `login_required` au niveau de la fonction.

Exemples reperes:

- `kyc/views.py:2952` - `export_agents_excel`
- `kyc/views.py:3011` - `export_agents_excel_s`
- `kyc/views.py:3600` - `export_ppe`
- `kyc/views.py:3800` - `export_non_resid_pp`
- `kyc/views.py:3971` - `export_non_resid_pm`
- `kyc/views.py:4041` - `scoring`
- `kyc/views.py:4156` - `export_csv_scoring`
- `kyc/views.py:4375` - `clients_scorer`
- `kyc/views.py:4511` - `export_csv_scoring_clients`
- `kyc/views.py:5271` - `non_rens`
- `kyc/views.py:5359` - `export_csv_pp`
- `kyc/views.py:5435` - `export_csv_anom`
- `kyc/views.py:6272` - `devise`
- `kyc/views.py:6348` - `export_devise_pp`
- `kyc/views.py:6420` - `devise_pm`
- `kyc/views.py:6503` - `export_devise_pm`

Risque:

- Fuite massive de donnees client/KYC si une route est accessible sans session.
- Acces inter-filiale si les filtres ne sont pas appliques partout.

Corrections recommandees:

- Appliquer `@login_required` a tous les exports.
- Centraliser les filtres de perimetre utilisateur.
- Interdire par defaut et ouvrir explicitement par role.
- Journaliser les exports sensibles.

Checklist:

- [ ] Ajouter `@login_required` sur tous les exports.
- [ ] Verifier les filtres filiale/agence/exploitant.
- [ ] Ajouter logs d'audit export.
- [ ] Tester qu'un utilisateur ne peut pas exporter hors perimetre.

### 5. Uploads OCR/PDF/ZIP insuffisamment limites

Constats:

- `KycDocumentExtraction.objects.select_related("uploaded_by").all()` expose tout le corpus documentaire a la fonction de filtrage.
- Uploads PDF/ZIP/images traites avec OCR sans limites applicatives visibles.
- Pas de limite explicite `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` dans `settings.py`.

Fichiers:

- `kyc/views.py:1649`
- `kyc/views.py:2174`
- `kyc/views.py:2190`
- `kyc/views.py:2214`
- `kyc/views.py:2251`
- `kyc/models.py:147`

Risque:

- Fuite documentaire inter-utilisateur ou inter-filiale.
- Denial of Service via gros PDF, ZIP volumineux, zip bomb ou OCR couteux.
- Stockage de documents sensibles sous `MEDIA_ROOT`.

Corrections recommandees:

- Filtrer les documents selon `uploaded_by`, `filiale`, role ou perimetre metier.
- Limiter taille fichier, nombre de fichiers, nombre de pages PDF et taille de ZIP.
- Rejeter les ZIP avec ratio de compression suspect.
- Stocker les documents sensibles hors repertoire servi publiquement.
- Nettoyer/expirer les fichiers temporaires.

Checklist:

- [ ] Ajouter limites de taille.
- [ ] Ajouter limite nombre de fichiers/pages.
- [ ] Filtrer les documents par perimetre utilisateur.
- [ ] Verifier la configuration de service des medias.
- [ ] Ajouter tests d'upload abusif.

### 6. Dependances Python vulnerables ou incoherentes

Constats:

- `requirements.txt` indique `Django==5.2.4`.
- `requirements2.txt` indique `Django==5.0.14`.
- L'environnement Python actif indique `Django==4.2.20`.
- `pip-audit` n'est pas installe localement.
- OSV signale des vulnerabilites pour plusieurs versions/packages:
  - Django 5.2.4
  - Django 5.0.14
  - Django 4.2.20
  - requests 2.27.1
  - urllib3 1.26.9
  - pillow 10.4.0
  - sqlparse 0.4.2
  - cryptography 45.0.5
  - pypdf 5.7.0

Sources consultees:

- Django security release 5.2.14, 2026-05-05: https://www.djangoproject.com/weblog/2026/may/05/security-releases/
- Django security release 5.2.13, 2026-04-07: https://www.djangoproject.com/weblog/2026/apr/07/security-releases/
- Django security release 5.2.6, 2025-09-03: https://www.djangoproject.com/weblog/2025/sep/03/security-releases/
- Django 5.2.9 release notes, 2025-12-02: https://docs.djangoproject.com/fr/6.0/releases/5.2.9/

Corrections recommandees:

- Choisir un seul fichier de requirements de reference.
- Mettre Django a jour vers une version maintenue et corrigee, idealement `5.2.14` ou plus recent compatible.
- Installer et integrer `pip-audit` ou `osv-scanner` dans le processus de livraison.
- Mettre a jour `requests`, `urllib3`, `pillow`, `sqlparse`, `pypdf`, `cryptography` apres tests.

Checklist:

- [ ] Unifier `requirements.txt` et `requirements2.txt`.
- [ ] Mettre a jour Django.
- [ ] Lancer `pip-audit`.
- [ ] Lancer les tests applicatifs apres upgrades.
- [ ] Ajouter un scan dependances en CI ou script de release.

## Moyen

### 7. Alertes `manage.py check --deploy`

Commande lancee:

```powershell
python manage.py check --deploy
```

Alertes:

- `SECURE_HSTS_SECONDS` non defini.
- `SECURE_SSL_REDIRECT` non defini a `True`.
- `SESSION_COOKIE_SECURE` non defini a `True`.
- `CSRF_COOKIE_SECURE` non defini a `True`.
- `DEBUG=True`.

Corrections recommandees:

- Activer les cookies securises en HTTPS.
- Activer HSTS apres validation complete du HTTPS.
- Configurer la redirection HTTPS au niveau reverse proxy et/ou Django.

Checklist:

- [ ] `SESSION_COOKIE_SECURE=True`.
- [ ] `CSRF_COOKIE_SECURE=True`.
- [ ] `SECURE_SSL_REDIRECT=True` si gere par Django.
- [ ] `SECURE_HSTS_SECONDS` defini apres validation.
- [ ] `SECURE_HSTS_INCLUDE_SUBDOMAINS=True` si applicable.
- [ ] `SECURE_HSTS_PRELOAD=True` si applicable.

### 8. Configuration SQL Server de secours affaiblie

Constat:

- `settings_secours.py` contient `TrustServerCertificate=yes;Encrypt=no;`.

Fichier:

- `Fiabilisation_kyc/settings_secours.py:105`

Risque:

- Connexion SQL Server non chiffree ou certificat non verifie.

Corrections recommandees:

- Utiliser `Encrypt=yes`.
- Eviter `TrustServerCertificate=yes` en production.
- Installer/valider un certificat serveur correct.

Checklist:

- [ ] Revoir la chaine de connexion SQL Server.
- [ ] Activer le chiffrement.
- [ ] Valider le certificat.

### 9. Politique mot de passe incomplete

Constat:

`AUTH_PASSWORD_VALIDATORS` contient seulement:

- `MinimumLengthValidator`
- `NumericPasswordValidator`

Fichiers:

- `Fiabilisation_kyc/settings.py:146`
- `Fiabilisation_kyc/settings_secours.py:113`

Corrections recommandees:

- Ajouter `UserAttributeSimilarityValidator`.
- Ajouter `CommonPasswordValidator`.
- Definir une longueur minimale adaptee.
- Eventuellement ajouter une politique interne pour complexite et rotation selon les exigences metier.

Checklist:

- [ ] Ajouter validateurs Django manquants.
- [ ] Tester creation/reset utilisateur.
- [ ] Documenter la politique de mot de passe.

## Faible / Hygiene

### 10. Fichiers de secours et duplications

Constats:

- `kyc/views_secours190925.py` et `kyc/sec.py` contiennent de nombreuses anciennes vues avec `csrf_exempt`.
- Meme si elles ne sont pas forcement routees, elles augmentent le risque de reutilisation accidentelle.

Corrections recommandees:

- Supprimer les fichiers legacy non utilises.
- Les archiver hors code applicatif si necessaire.

Checklist:

- [ ] Verifier si `kyc/sec.py` est importe.
- [ ] Verifier si `kyc/views_secours190925.py` est utilise.
- [ ] Supprimer ou isoler les anciens fichiers.

## Outils executes

Commandes locales:

```powershell
python manage.py check --deploy
npm audit --omit=dev --json
rg "...patterns securite..." -S
git ls-files ...
```

Resultats:

- `manage.py check --deploy`: 5 alertes securite.
- `npm audit --omit=dev`: 0 vulnerabilite production detectee cote Node.
- `bandit`: non execute, module non installe.
- `pip-audit`: non execute, module non installe.
- OSV API: interrogee pour les dependances Python principales.

## Plan de correction recommande

### Phase 1 - Bloquants production

- [ ] Corriger `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`.
- [ ] Activer cookies securises et HTTPS.
- [ ] Retirer les donnees sensibles du depot.
- [ ] Supprimer les `csrf_exempt` sur vues metier.
- [ ] Ajouter `login_required` et autorisations aux vues sensibles.

### Phase 2 - Donnees KYC et perimetres

- [ ] Centraliser un helper de filtrage par utilisateur.
- [ ] Appliquer ce helper aux exports et tableaux.
- [ ] Ajouter logs d'audit sur exports/imports/reset password.
- [ ] Restreindre documents OCR par proprietaire/perimetre.

### Phase 3 - Dependances et qualite

- [ ] Unifier les requirements.
- [ ] Mettre a jour Django et dependances vulnerables.
- [ ] Installer `pip-audit` ou `osv-scanner`.
- [ ] Ajouter tests de securite basiques.
- [ ] Nettoyer fichiers legacy.

## Notes

Ce rapport est un scan statique et configurationnel. Il ne remplace pas un test d'intrusion complet avec environnement de preproduction, comptes par roles, reverse proxy, base SQL Server cible et donnees anonymisees.
