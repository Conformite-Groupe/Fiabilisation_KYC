# Rapport de vulnérabilités — Plateforme Fiabilisation KYC

**Date du scan :** 2026-07-24
**Périmètre :** code applicatif Django (`kyc/`, `accounts/`, `Fiabilisation_kyc/`, `templates/`), configuration, dépôt Git.
**Méthode :** audit statique (revue de code, analyse des routes et des décorateurs, recherche de motifs dangereux, inspection du dépôt Git). Aucun test dynamique / d'intrusion, aucune modification du code.
**Branche auditée :** `main` (dernier commit `4571f72`).
**Rapport précédent :** `RAPPORT_VULNERABILITES.md` (2026-06-04) — remplacé par le présent document.

---

## Synthèse exécutive

La configuration Django a été nettement durcie depuis le rapport du 2026-06-04 : `SECRET_KEY` lue depuis `.env`, `DEBUG` piloté par variable d'environnement, HSTS, cookies `Secure`/`HttpOnly`, `django-axes`, validateurs de mot de passe, journalisation de sécurité, et suppression des `@csrf_exempt` sur les vues d'authentification. Les vues réellement routées sont **toutes** protégées par `@login_required`, et les vues sensibles (audit, création d'utilisateur, réinitialisation de mot de passe, imports) portent un contrôle d'autorisation par organe ou `is_superuser`.

Il subsiste néanmoins **2 vulnérabilités critiques** qui doivent être traitées avant toute exposition en production :

1. Un endpoint d'import d'utilisateurs en masse sans contrôle d'autorisation, permettant à n'importe quel compte authentifié de se créer un administrateur (`organe=PASS`) → **élévation de privilège complète**.
2. Le fichier `Fiabilisation_kyc/.env`, contenant la `SECRET_KEY` de production, est **versionné dans Git** et présent dans tout l'historique.

| Sévérité | Nombre |
|---|---|
| Critique | 2 |
| Élevée | 4 |
| Moyenne | 6 |
| Faible | 5 |

---

## Critique

### C-1 — Élévation de privilège via l'import CSV d'utilisateurs

**Fichier :** `kyc/views.py:8969-9015` (`bulk_user_upload`) — route `/bulk-upload/` (`Fiabilisation_kyc/urls.py`)

La vue est protégée par `@login_required` **et rien d'autre**. Aucun contrôle sur `request.user.organe`, contrairement à toutes les autres vues de gestion des comptes (`register`, `edit_user`, `reset_user_password` vérifient `organe in ["PASS", "DSI"]`).

```python
@login_required
def bulk_user_upload(request):
    if request.method == "POST":
        csv_file = request.FILES.get('file')
        ...
        user, created = User.objects.get_or_create(
            username=row[0],
            defaults={..., 'organe': row[3], ...})
        if created:
            user.set_password(row[5])
```

**Scénario d'exploitation :** un utilisateur légitime au profil le plus bas (par exemple « Chargé Client ») POSTe sur `/bulk-upload/` un CSV d'une ligne :
`attaquant@boa.local,X,Y,PASS,000,MotDePasse123!,AG,EXPL999`
Il obtient un compte d'organe **PASS** dont il connaît le mot de passe, donc l'accès à la totalité des filiales, à la gestion des comptes, aux exports et à la piste d'audit.

Facteurs aggravants :
- La valeur `organe` provient directement du CSV, sans liste blanche ni restriction à la filiale de l'appelant (là où `register` force `new_user.filiale = current_user.filiale` pour un DSI).
- Aucun appel à `log_audit(...)` : les comptes créés par ce canal n'apparaissent pas dans la piste d'audit, contrairement à `reset_user_password`.
- Les exceptions sont avalées (`except Exception: errors += 1; continue`), l'attaque est donc silencieuse.

**Correction :** ajouter en tête de la vue le même garde que `register`, restreindre `organe` à une liste blanche, forcer la filiale pour les DSI, et journaliser chaque création via `log_audit`.

```python
@login_required
def bulk_user_upload(request):
    if request.user.organe not in ("PASS", "DSI"):
        messages.error(request, "Vous n'avez pas la permission de créer des comptes.")
        return redirect('accueil')
```

---

### C-2 — Fichier `.env` de production versionné dans Git (SECRET_KEY exposée)

**Fichiers :** `Fiabilisation_kyc/.env`, `.gitignore`

Le `.gitignore` contient bien `.env` et `.env.*`, mais **le fichier a été ajouté au suivi Git avant cette règle** : `.gitignore` n'a aucun effet sur un fichier déjà suivi. Le fichier est donc committé et versionné :

```
$ git ls-files | grep .env
Fiabilisation_kyc/.env
$ git log --oneline -- Fiabilisation_kyc/.env
08ed120 07072026
ac68e60 25062026
ea4a29b Initial commit propre sans base sqlite
```

Il contient en clair la `SECRET_KEY` Django, les `ALLOWED_HOSTS` et les paramètres de connexion.

**Impact :** toute personne ayant accès au dépôt (ou à une copie, une archive, un poste de développeur) détient la `SECRET_KEY`. Avec cette clé, un attaquant peut **forger des cookies de session signés et se faire passer pour n'importe quel utilisateur**, y compris un compte PASS, sans jamais connaître de mot de passe. Elle permet aussi de forger des jetons de réinitialisation de mot de passe et des jetons CSRF.

Le commit `ea4a29b` s'intitule « Initial commit propre sans base sqlite », ce qui indique qu'un nettoyage a été tenté mais n'a pas couvert le `.env`.

**Correction :**
1. **Considérer la clé actuelle comme compromise** et en générer une nouvelle :
   `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
2. Retirer le fichier du suivi sans le supprimer du disque : `git rm --cached Fiabilisation_kyc/.env`, puis commit.
3. Purger l'historique (`git filter-repo --path Fiabilisation_kyc/.env --invert-paths`) si le dépôt est partagé ou poussé sur un remote.
4. Committer un `Fiabilisation_kyc/.env.example` documentant les clés attendues, sans valeurs.

---

## Élevée

### E-1 — `DEBUG=True` et cookies non sécurisés dans le `.env` livré

**Fichier :** `Fiabilisation_kyc/.env`

Le fichier de configuration présent dans le dépôt porte les valeurs suivantes :

```
DEBUG=True
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_HSTS_SECONDS=0
```

Les valeurs par défaut de `settings.py` sont correctes (`DEBUG=False`, cookies `Secure` quand `DEBUG=False`, HSTS 1 an) — c'est bien le `.env` qui les neutralise toutes. Si ce fichier est déployé tel quel :
- `DEBUG=True` expose la page d'erreur Django complète : traceback, extraits de code, **contenu des settings et des variables d'environnement**, requêtes SQL. Sur une plateforme KYC, cela signifie une fuite directe de données clients à la première exception non gérée.
- `DEBUG=True` fait aussi que `ALLOWED_HOSTS` n'est plus réellement contraignant et que `static(settings.MEDIA_URL, ...)` en fin de `urls.py` sert **le dossier `media/` sans aucune authentification** — or `media/document_extraction/` contient les pièces d'identité téléversées (voir E-2).
- Les cookies de session circulent en clair (`Secure=False`) et sont donc interceptables sur le réseau.

**Correction :** basculer le `.env` de production sur `DEBUG=False`, `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`, `SECURE_HSTS_SECONDS=31536000`. Maintenir un `.env` distinct pour le poste de développement, jamais versionné.

---

### E-2 — Documents KYC téléversés servis sans contrôle d'accès

**Fichiers :** `Fiabilisation_kyc/urls.py` (dernière ligne), `kyc/models.py:256`

```python
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

```python
uploaded_file = models.FileField(upload_to='document_extraction/')
```

Les pièces d'identité et justificatifs analysés par le module d'extraction sont stockés sous `media/document_extraction/` et exposés sous `/media/...`. Cette route ne passe par **aucune vérification d'authentification ni de cloisonnement par filiale** : l'URL seule suffit. Le nom du fichier étant celui d'origine (ou une variante prévisible), l'énumération est envisageable.

Précision : `django.conf.urls.static.static()` renvoie une liste vide lorsque `DEBUG=False`, donc en configuration de production correcte Django ne sert pas ces fichiers — mais **la configuration livrée est `DEBUG=True`** (E-1), et si un reverse proxy (Nginx/IIS) est configuré pour servir `/media/` directement, le problème persiste indépendamment de `DEBUG`.

**Correction :** sortir `MEDIA_ROOT` de toute racine servie publiquement, et exposer les documents via une vue Django dédiée qui vérifie `request.user` et la filiale du document, puis renvoie un `FileResponse` (ou délègue à Nginx via `X-Accel-Redirect`). Supprimer l'appel `static(settings.MEDIA_URL, ...)` de `urls.py`.

---

### E-3 — Django 5.2.4 : version vulnérable connue

**Fichier :** `requirements.txt`, environnement virtuel (`Django 5.2.4` confirmé à l'exécution)

La branche 5.2 a reçu plusieurs correctifs de sécurité postérieurs à la 5.2.4, dont une injection SQL exploitable via les alias de colonnes dans `QuerySet.annotate()/alias()/aggregate()` et des correctifs de déni de service. Une plateforme qui construit dynamiquement des requêtes d'agrégation (ce qui est massivement le cas dans `kyc/views.py` et `kyc/pilotage_exports.py`) est directement dans le périmètre concerné.

**Correction :** monter sur le dernier correctif de la branche 5.2 LTS (`pip install --upgrade "Django>=5.2.8,<6.0"`), puis rejouer la suite de tests (`kyc/tests.py`). Mettre en place un contrôle régulier via `pip-audit` ou `safety`.

---

### E-4 — Base SQLite de production (510 Mo) et caches de données dans le dépôt

**Fichiers :** `db.sqlite3` (510 Mo), `db.sqlite3-wal`, `db.sqlite3-shm`, `.django_cache/*.djcache` (32 fichiers suivis), `logs/import_*.log`, `django.log`

Le `.gitignore` liste `db.sqlite3`, mais les fichiers annexes `db.sqlite3-shm` et `db.sqlite3-wal` **sont suivis par Git** (ce sont les journaux WAL de SQLite : ils contiennent des pages de données réelles, non encore fusionnées dans le fichier principal). Sont également suivis :

- 32 fichiers `.django_cache/*.djcache` — sérialisations des tableaux de bord, qui contiennent des agrégats et potentiellement des données clients ;
- l'ensemble des journaux d'import (`logs/import_kyc.log`, `logs/import_runs/*.log`) — les journaux d'import KYC comportent typiquement des identifiants clients et des messages d'erreur incluant des valeurs de champs ;
- `django.log`, `django.pid`, `ocr_worker.pid`.

**Impact :** diffusion de données à caractère personnel de clients bancaires hors du périmètre applicatif, via un canal (le dépôt de code) qui n'est ni chiffré ni tracé au titre de la protection des données.

**Correction :** `git rm --cached` sur ces chemins, compléter le `.gitignore` (`*.djcache`, `.django_cache/`, `db.sqlite3-*`, `logs/`, `*.pid`, `*.log`), et purger l'historique si le dépôt est partagé. Par ailleurs, SQLite n'est pas un moteur adapté à une base de 510 Mo en accès concurrent : la configuration MSSQL présente en commentaire dans `settings.py` devrait être activée en production (voir M-6).

---

## Moyenne

### M-1 — Modules morts truffés de `@csrf_exempt` et de vues non protégées

**Fichiers :** `kyc/sec.py` (394 lignes, 9 `@csrf_exempt`), `kyc/views_secours190925.py` (2056 lignes, 19 `@csrf_exempt`), `accounts/views.py:20-30`

Aucun de ces modules n'est référencé par `Fiabilisation_kyc/urls.py` ni par `kyc/urls.py` : ils sont donc **actuellement inexploitables**. Ils constituent néanmoins une dette de sécurité sérieuse, car ils contiennent des variantes anciennes des vues en production, dépourvues de contrôles :

- `kyc/sec.py:342` — `user_list()` sans `@login_required` et sans filtrage par organe : renvoie `ProfileV.objects.all()` à tout visiteur.
- `kyc/sec.py:326` — `register()` sans aucun contrôle : création de compte anonyme.
- `kyc/sec.py:148` — première définition de `reset_user_password()` sans décorateur (masquée par la redéfinition ligne 380, comportement fragile).
- `kyc/sec.py:212`, `260`, `129` — `perso_stock`, `notes`, `profile` accèdent à `request.user.filiale` sans `@login_required` : plantage sur `AnonymousUser` au mieux, fuite au pire.
- `accounts/views.py:21` — `register()` crée un utilisateur **à partir des paramètres GET** (`if len(request.GET) > 0: form.save()`) : création de compte par simple URL, sans POST ni CSRF.

Une seule ligne ajoutée dans `urls.py` par inadvertance rend l'une de ces vues exploitable.

**Correction :** supprimer `kyc/sec.py` et `kyc/views_secours190925.py` du dépôt (l'historique Git conserve la trace si besoin), et supprimer la fonction `register` de `accounts/views.py`.

---

### M-2 — La réinitialisation de mot de passe n'applique aucun validateur

**Fichier :** `kyc/forms.py:276-307` (`ResetPasswordForm`), utilisé par `kyc/views.py:4579` (`reset_user_password`)

Le `clean()` du formulaire ne vérifie **que** l'égalité des deux saisies :

```python
def clean(self):
    ...
    if new_password != confirm_password:
        raise forms.ValidationError("Les mots de passe ne correspondent pas.")
    return cleaned_data
```

Les `AUTH_PASSWORD_VALIDATORS` configurés dans `settings.py` (longueur ≥ 10, mots de passe communs, tout-numérique, similarité avec l'identifiant) ne sont **jamais** appelés sur ce chemin, car `validate_password()` n'est pas invoqué. Un administrateur PASS ou DSI peut donc attribuer `1234` comme mot de passe à un compte. Combiné à C-1, c'est aussi le chemin le plus court pour poser un mot de passe faible sur un compte privilégié.

**Correction :**

```python
from django.contrib.auth.password_validation import validate_password

def clean(self):
    cleaned_data = super().clean()
    new_password = cleaned_data.get("new_password")
    if new_password != cleaned_data.get("confirm_password"):
        raise forms.ValidationError("Les mots de passe ne correspondent pas.")
    if new_password:
        validate_password(new_password, self.instance)
    return cleaned_data
```

---

### M-3 — Absence de validation du type des fichiers téléversés

**Fichier :** `kyc/views.py:3159-3215` (`document_extraction`)

Le module contrôle correctement la taille (`SINGLE_FILE_MAX_BYTES`) et se prémunit contre les archives ZIP piégées (`ZIP_MAX_MEMBERS`, contrôle de la taille décompressée) — bon point. En revanche, **aucune vérification du type réel** du fichier n'est faite : ni sur l'extension (hors le cas `.zip`), ni sur le type MIME, ni sur les octets d'en-tête. N'importe quel contenu (`.html`, `.svg`, `.exe`, `.py`) est accepté, stocké sous `media/document_extraction/` avec son nom d'origine, puis transmis aux moteurs OCR/PDF (RapidOCR, PyMuPDF).

Deux conséquences :
- Couplé à E-2, un `.html` ou `.svg` téléversé et servi depuis `/media/` s'exécute dans l'origine de l'application → **XSS stockée** avec vol de session.
- Les parseurs binaires (PyMuPDF) sont exposés à des fichiers arbitraires, augmentant la surface d'attaque mémoire.

**Correction :** valider par liste blanche d'extensions (`.pdf`, `.jpg`, `.jpeg`, `.png`, `.tiff`, `.zip`), recouper avec la signature binaire (magic bytes) et servir les médias avec `Content-Disposition: attachment` et `X-Content-Type-Options: nosniff`.

---

### M-7 — Endpoint latent de réinitialisation de mot de passe sans aucun contrôle *(ajouté le 2026-07-24)* ✅ **Corrigé**

**Fichier :** `kyc/views.py` (ancienne `reset_user_password_b`), `Fiabilisation_kyc/urls.py`

La vue `reset_user_password_b(request, user_id)` réinitialisait le mot de passe de **n'importe quel compte** désigné par `user_id`, **sans `@login_required` ni contrôle d'organe** — aucune protection. Sa route était commentée dans `urls.py` (`#path('modify-pw/<int:user_id>/', ...)`), donc non exploitable en l'état, mais la vue était importée et une seule ligne décommentée en aurait fait un endpoint de réinitialisation de mot de passe **anonyme** pour tout compte, y compris un PASS. Même classe de risque que les modules morts de M-1.

**Correction (2026-07-24) :** vue supprimée, retirée de l'import et la ligne de route commentée effacée dans `urls.py`. La réinitialisation passe désormais uniquement par `reset_user_password()`, protégée (`@login_required` + organe + filiale + `validate_password` via M-2). Vérifié : `manage.py check` propre, l'URL `modify-pw` continue de résoudre vers la vue active `ChangePasswordView`, suite de tests inchangée (31/34, 3 échecs préexistants).

---

### M-4 — Modèle `Person` stockant des mots de passe en clair

**Fichiers :** `kyc/models.py:644-653`, `kyc/forms.py:17-30` (`LoginForm`)

```python
class Person(models.Model):
    ...
    password = models.CharField(blank=True, max_length=32, default='')
```

```python
class LoginForm(forms.Form):
    ...
    result = Person.objects.filter(password=password, ...)
```

Le champ stocke un mot de passe **non haché** (`max_length=32` confirme qu'il ne s'agit pas d'un hachage Django, qui fait ~78+ caractères), et `LoginForm` l'authentifie par comparaison directe en base. Ce chemin n'est plus routé (l'authentification en production passe par `accounts.views.login_kyc` → `authenticate()`, correct), mais la table existe toujours en base et peut contenir des mots de passe historiques en clair — réutilisés ailleurs par les utilisateurs.

**Correction :** vérifier le contenu de la table `kyc_person` en production ; si elle contient des mots de passe, les purger. Supprimer le champ `password` du modèle (via migration) ainsi que la classe `LoginForm`.

---

### M-5 — `requirements.txt` incomplet et illisible

**Fichier :** `requirements.txt`

Le fichier est encodé en **UTF-16** (avec BOM), ce qui le rend inexploitable par `pip install -r` sur la plupart des configurations. Il ne liste par ailleurs que 12 paquets, alors que l'application importe entre autres `django-environ`, `whitenoise`, `crispy-forms`, `crispy-tailwind`, `django-tailwind`, `django-countries`, `openpyxl`, `mssql-django`/`pyodbc` — tous absents.

**Impact sécurité :** impossible de reconstruire un environnement à l'identique, donc impossible d'auditer les versions réellement déployées ou de faire tourner un scanner de vulnérabilités de dépendances de façon fiable. Un déploiement reconstruit depuis ce fichier échouera ou installera des versions arbitraires.

**Correction :** régénérer en UTF-8 depuis l'environnement de référence (`pip freeze > requirements.txt`), et le placer sous contrôle d'un scan automatisé (`pip-audit`).

---

### M-6 — Base SQLite en production et identifiants MSSQL en dur

**Fichier :** `Fiabilisation_kyc/settings.py:205-226`

La base `default` est SQLite (fichier de 510 Mo), et la base `prod` déclare en dur l'hôte MSSQL `10.170.83.20:1433` avec `TrustServerCertificate=yes`.

- SQLite ne fournit ni chiffrement au repos, ni gestion de comptes, ni journalisation d'accès : pour des données KYC bancaires, la protection repose uniquement sur les droits du système de fichiers. Les écritures concurrentes (workers `run_daily_jobs`) reposent sur un simple `timeout: 60`.
- `TrustServerCertificate=yes` **désactive la validation du certificat TLS** de la connexion MSSQL : la liaison applicatif ↔ base est vulnérable à une interception active sur le réseau interne.
- L'adresse du serveur de base de production est écrite en clair dans un fichier versionné (reconnaissance facilitée).

**Correction :** basculer `default` sur MSSQL, externaliser hôte/nom/identifiants dans le `.env`, et retirer `TrustServerCertificate=yes` au profit d'un certificat serveur validé par l'autorité interne.

---

## Faible

### F-1 — Déconnexion accessible en GET
`accounts/views.py:82` (`logout_user`) traite toute requête, y compris GET. Une balise `<img src="https://.../logout/">` sur un site tiers déconnecte l'utilisateur (nuisance CSRF sans gain pour l'attaquant). Restreindre via `@require_POST`.

### F-2 — Pas de limitation de débit sur le changement de mot de passe forcé
`accounts/views.py:55` (`force_password_change`) s'appuie sur `request.session['force_pw_user_id']` posé avant `login()`. `django-axes` protège le formulaire de login mais pas cette étape intermédiaire. Le risque est limité (l'identifiant de session est nécessaire), mais la session est fixée avant authentification complète : ajouter un appel à `request.session.cycle_key()` après le changement réussi.

### F-3 — Absence d'en-tête `Content-Security-Policy`
Aucune CSP n'est définie dans `settings.py` ni dans le middleware. En défense en profondeur contre le XSS (voir M-3), ajouter `django-csp` avec une politique restrictive (`default-src 'self'`).

### F-4 — `SECURE_BROWSER_XSS_FILTER` obsolète
`settings.py:111` — l'en-tête `X-XSS-Protection` est ignoré par tous les navigateurs modernes et a été retiré ; il a même introduit des vulnérabilités par le passé. À remplacer par une CSP (F-3). Sans impact direct.

### F-5 — `INTERNAL_IPS` contient `0.0.0.0`
`settings.py:297-299` — `INTERNAL_IPS = ["127.0.0.1", "10.170.82.20", "0.0.0.0"]`. Sans `django-debug-toolbar` installé, l'effet est limité au contexte de template `debug`. `0.0.0.0` n'est de toute façon jamais une adresse cliente valide : à retirer.

---

## Points positifs relevés

Ces éléments sont conformes et méritent d'être maintenus :

- **Toutes** les vues routées portent `@login_required` (vérifié route par route sur `Fiabilisation_kyc/urls.py` et `kyc/urls.py`).
- Cloisonnement par filiale correctement implémenté sur les vues sensibles : `audit_views.audit_view` ignore explicitement le paramètre `filiale` de l'URL quand un périmètre est imposé (`kyc/audit_views.py:309-315`).
- Protection IDOR effective sur les travaux de rapprochement documentaire : `document_extraction_match_job_status` appelle `_user_can_access_document_match_job()` et renvoie 403 (`kyc/views.py:2261-2265`).
- `import_log_download` filtre correctement la traversée de répertoire (rejet de `..`, `/`, `\`) **et** restreint aux chemins d'une liste blanche, avec garde `is_superuser` (`kyc/views.py:3972-3989`).
- Les imports lancés par `import_page` utilisent `subprocess.run` avec une liste d'arguments et un nom de script issu d'une liste fermée — **pas d'injection de commande** possible (`kyc/views.py:1145-1176`).
- Aucun SQL brut dans le code applicatif : les seuls `cursor()` sont dans les migrations et une commande d'administration.
- Aucun `eval`, `exec`, ni `pickle.loads`.
- Aucun `|safe` ni `{% autoescape off %}` dans les templates : l'échappement automatique de Django n'est nulle part contourné.
- Protections anti zip-bomb sur l'import d'archives (nombre de membres et taille décompressée bornés).
- `django-axes` avec seuils pilotables depuis l'admin, et journalisation de sécurité dédiée avec rotation.
- Piste d'audit (`log_audit`) sur les opérations sensibles de gestion de compte.

---

## Plan de remédiation proposé

| Priorité | Action | Réf. | État |
|---|---|---|---|
| **Immédiat — avant mise en production** | Ajouter le contrôle d'organe sur `bulk_user_upload` | C-1 | ✅ **Corrigé le 2026-07-24** |
| **Immédiat** | Désuivre `.env` de Git, publier un `.env.example` | C-2 | ✅ **Corrigé le 2026-07-24** |
| **Immédiat** | Régénérer la `SECRET_KEY` et purger l'historique Git | C-2 | ⬜ À faire (voir ci-dessous) |
| **Immédiat** | Passer le `.env` de production en `DEBUG=False` + cookies `Secure` | E-1 | ⬜ À faire |
| **Immédiat** | Retirer `static(MEDIA_URL, ...)` et servir les documents via une vue contrôlée | E-2 | ✅ **Corrigé le 2026-07-24** — ⚠️ voir prérequis reverse proxy |
| Court terme (1 sem.) | Mettre à jour Django ≥ 5.2.8 | E-3 | ✅ **Corrigé le 2026-07-24** (5.2.16) |
| Court terme | Désuivre base, caches et journaux ; compléter `.gitignore` | E-4 | ✅ **Corrigé le 2026-07-24** |
| Court terme | Supprimer `kyc/sec.py`, `kyc/views_secours190925.py`, `accounts.views.register` | M-1 | ✅ **Corrigé le 2026-07-24** |
| Court terme | Appliquer `validate_password()` dans `ResetPasswordForm` | M-2 | ✅ **Corrigé le 2026-07-24** |
| Moyen terme (1 mois) | Valider extension + signature des fichiers téléversés | M-3 | ✅ **Corrigé le 2026-07-24** (uploads directs ; membres de ZIP à couvrir) |
| Moyen terme | Purger et supprimer le champ `Person.password` | M-4 | ⬜ À faire (migration DB — voir note) |
| Moyen terme | Régénérer `requirements.txt` en UTF-8 ; intégrer `pip-audit` en CI | M-5 | ✅ Fichier régénéré ; reste `pip-audit` en CI |
| Moyen terme | Basculer sur MSSQL, externaliser les identifiants, TLS validé | M-6 | ⬜ À faire |
| Amélioration continue | Nettoyage `INTERNAL_IPS` | F-5 | ✅ **Corrigé le 2026-07-24** |
| Amélioration continue | `@require_POST` sur logout, CSP | F-1, F-3 | ⬜ À faire (F-1 : voir note) |

---

## Correctifs appliqués le 2026-07-24

Modifications apportées au dépôt lors de cette session. **Aucun commit n'a été effectué** : les changements sont dans la copie de travail et l'index Git.

**C-1 — `kyc/views.py` (`bulk_user_upload`)**
- Ajout du garde `if current_user.organe not in ("PASS", "DSI")` en tête de vue, aligné sur `register()`.
- `organe` validé contre une liste blanche construite depuis les choix du modèle (`Organe`), au lieu d'être repris tel quel du CSV.
- Un DSI ne peut plus créer de compte `PASS`, et la filiale des comptes qu'il crée est forcée à la sienne (cohérent avec `register()`).
- Chaque création est tracée via `log_audit(category=AuditEvent.CAT_SECURITE)`.
- Les lignes refusées sont remontées à l'utilisateur au lieu d'être silencieusement comptées en erreurs.
- Import de `Organe` ajouté ligne 58.

**C-2 / E-4 — dépôt Git** (fichiers retirés de l'index, **conservés sur disque**)
- `git rm --cached Fiabilisation_kyc/.env`
- `git rm --cached` sur `db.sqlite3-shm`, `db.sqlite3-wal`, `django.log`, `django.pid`, `ocr_worker.pid`, `.django_cache/` (32 fichiers), `logs/` (16 fichiers)
- `.gitignore` complété : `db.sqlite3-*`, `.django_cache/`, `*.djcache`, `logs/`, `*.pid`, plus l'exception `!.env.example`
- Nouveau fichier `Fiabilisation_kyc/.env.example` documentant les clés attendues avec les **valeurs de production** (`DEBUG=False`, cookies `Secure`, HSTS 1 an), sans aucun secret

**E-2 — service contrôlé des fichiers `media/`**
- `Fiabilisation_kyc/urls.py` : suppression de `+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)`, remplacé par `re_path(r'^media/(?P<path>.*)$', views.serve_protected_media)`. Imports `static` et `settings`, devenus inutilisés, retirés.
- `kyc/views.py` : nouvelle vue `serve_protected_media()` et helpers `_user_is_group_scope()` / `_user_can_access_extraction_file()`.

Règles appliquées :

| Chemin | Accès |
|---|---|
| `media/images/` (logo, marque) | **Public** — nécessaire aux pages sans session (connexion, verrouillage Axes, changement de mot de passe forcé) |
| `media/document_extraction/` | Authentifié **+** périmètre : superutilisateur, profil groupe, déposant du document, ou même filiale que le déposant. Sinon **403 + trace d'audit** |
| Autres (`profile_avatars/`, divers) | Authentifié |

- Le cloisonnement par filiale s'appuie sur `uploaded_by.filiale`, le modèle `KycDocumentExtraction` ne portant pas de champ `filiale`. La logique « profil groupe » reprend celle du module d'extraction.
- Les fichiers **orphelins** (présents sur disque sans enregistrement en base) sont refusés par défaut, sauf superutilisateur.
- Traversée de répertoire bloquée par résolution du chemin et vérification d'appartenance à `MEDIA_ROOT` (couvre `../`, `..\`, et `images/../../` qui aurait pu contourner via le préfixe public).
- Les documents KYC sont servis en `Content-Disposition: attachment` avec `X-Content-Type-Options: nosniff` et `Cache-Control: private, no-store` : neutralise le risque de XSS stockée décrit en M-3, même si un fichier piégé est téléversé.

> ⚠️ **Prérequis de déploiement.** Cette protection n'a d'effet que si le reverse proxy (Nginx / IIS) **ne sert pas `/media/` directement**. Toute directive de type `location /media/ { alias ...; }` court-circuiterait entièrement la vue et rétablirait la vulnérabilité. La configuration du proxy n'a pas été fournie : **à vérifier avant mise en production.** Si le volume de documents devient important, déléguer l'envoi via `X-Accel-Redirect` (Nginx) en conservant le contrôle d'accès dans la vue.

**E-3 — mise à jour de Django**
- `Django 5.2.4 → 5.2.16` (dernier correctif de la branche LTS 5.2 au moment de l'audit ; la 6.0 est volontairement écartée — version majeure porteuse de ruptures, à traiter comme un chantier distinct).
- `manage.py check` : aucune anomalie. Suite de tests rejouée : 24/27, strictement les mêmes 3 échecs préexistants, **aucune régression** liée à la montée de version.
- ⚠️ Une migration `choices` est en attente (`0065_alter_devise_filiale_and_more`), mais elle provient de modifications de modèles **non committées, sans rapport avec cette montée de version** ni avec la sécurité. Non générée ici : elle relève du travail applicatif en cours.

**M-5 — `requirements.txt` régénéré**
- Réécrit en **UTF-8** (il était en UTF-16, illisible par `pip install -r`), désormais **complet** (91 paquets épinglés au lieu de 12), dépendances directes regroupées et commentées, transitives épinglées pour la reproductibilité.
- Vérifié : `pip install -r requirements.txt --dry-run` résout l'intégralité du fichier sans erreur.

**Vérifications**
- `manage.py check` : aucune anomalie.
- 7 tests ajoutés (`kyc/tests.py`, classe `ProtectedMediaAccessTest`) couvrant : logo public, document refusé à l'anonyme, refus hors filiale, accès déposant, accès même filiale, traversée bloquée, fichier orphelin refusé. **Les 7 passent.**
- Contrôle de bout en bout contre les fichiers réels du projet (99 documents dans `media/document_extraction/`) :
  - anonyme → `/media/images/logo.png` : **200** (le logo reste affiché sur les pages de connexion)
  - anonyme → `/media/document_extraction/Document_scanne.pdf` : **302** vers `/login_kyc/?next=...`
  - superutilisateur → même document : **200**, `Content-Disposition: attachment`
- `manage.py test kyc accounts` : 24/27 succès (20 tests d'origine + 7 ajoutés). Les 3 échecs (`test_field_source_filtering_in_matching`, `test_propagate_field_sources_to_all_filiales`, `test_pm_matching_by_nif`) ont été confirmés **préexistants** en rejouant la suite sans le correctif : résultat identique avant et après. Ils portent sur le rapprochement documentaire et les sources de champs, sans lien avec les modifications. À traiter séparément.

**Reste à faire sur C-2 — nécessite une décision d'exploitation**

La `SECRET_KEY` actuelle doit être considérée comme compromise. Une clé de remplacement a été générée :

```
vj*w_bv@+8=$rr#*s&vlsh8k^dt*xnrw7#nhsge(3_$u9=4u7d
```

Elle n'a **pas** été installée : la rotation invalide toutes les sessions actives et déconnecte l'ensemble des utilisateurs, ce qui relève d'une fenêtre de maintenance.

> 🔴 **Aggravation confirmée pendant la session.** Le dépôt est poussé sur un remote GitHub : `origin → github.com/rcboaholding/fiabilisation_kyc.git`, avec les branches distantes `origin/main` et `origin/feature/creation-ongle-controleQualie`. Le `.env` (et donc la `SECRET_KEY`) est donc présent **sur GitHub, dans l'historique**, quelle que soit la visibilité du dépôt. Le désuivi appliqué localement n'efface rien du remote. La rotation de la clé n'est par conséquent **pas optionnelle** : elle doit être faite, et l'historique distant purgé.
>
> **Vérifier d'urgence** : la visibilité du dépôt (privé/public) sur `github.com/rcboaholding` — s'il est public, la `SECRET_KEY`, l'adresse du serveur MSSQL de production et les journaux d'import sont exposés publiquement.

Étapes (dans l'ordre) :
1. Installer l'outil : `pip install git-filter-repo` (absent de l'environnement — vérifié pendant la session).
2. Purger l'historique : `git filter-repo --path Fiabilisation_kyc/.env --invert-paths` (à étendre aux autres fichiers sensibles de E-4 : `db.sqlite3-*`, `logs/`, `.django_cache/`).
3. `git push --force` sur toutes les branches, coordonné avec les autres porteurs de clones.
4. Installer la nouvelle `SECRET_KEY` dans le `.env` de production.

Purger l'historique ne suffit pas à « dé-compromettre » la clé : elle a déjà pu être clonée. La rotation reste indispensable.

---

## Correctifs appliqués — 2e passe (2026-07-24)

Toujours **sans commit** ; changements dans la copie de travail.

**M-1 — modules morts supprimés**
- Suppression de `kyc/sec.py` et `kyc/views_secours190925.py` (non routés, non suivis par Git — vérifié). Ils contenaient des variantes anciennes de vues sans contrôle (`user_list` sans `@login_required`, `register` anonyme, ~28 `@csrf_exempt`).
- `accounts/views.py` : suppression de la fonction `register()` qui créait un compte **à partir des paramètres GET** (sans POST ni CSRF), et des imports devenus inutiles (`Utilisateur`, `Person`, `csrf_exempt`, `forms`).

**M-2 — validation du mot de passe à la réinitialisation**
- `kyc/forms.py` : `ResetPasswordForm.clean()` appelle désormais `validate_password(new_password, self.instance)`, activant les `AUTH_PASSWORD_VALIDATORS` (longueur ≥ 10, mots de passe communs, tout-numérique, similarité). C'est le chemin utilisé par la vue live `reset_user_password`.

**M-3 — validation du type des fichiers téléversés**
- `kyc/views.py` : constante `ALLOWED_DOCUMENT_EXTENSIONS` + table de signatures binaires `_FILE_SIGNATURES` + helper `_validate_uploaded_document()`, branché dans `document_extraction` juste après le filtre de taille. Chaque fichier est vérifié sur son extension (liste blanche) **et** ses octets d'en-tête ; un fichier au contenu incohérent avec l'extension (ex. HTML renommé `.pdf`) est refusé.
- ⚠️ **Limite** : la validation couvre les uploads directs. Les fichiers **extraits d'une archive ZIP** ne sont pas encore passés au même contrôle — à compléter (le reste des protections anti zip-bomb demeure).

**F-5 — `INTERNAL_IPS`**
- `settings.py` : retrait de `0.0.0.0`, jamais une adresse cliente valide.

**M-5 — `pip-audit`** : le fichier est régénéré (1re passe) ; reste à intégrer `pip-audit` en CI.

**Vérifications de cette passe**
- `manage.py check` : aucune anomalie.
- 7 tests ajoutés (`PasswordValidationOnResetTest`, `UploadedDocumentTypeValidationTest`) : mot de passe trivial/tout-numérique refusé, mot de passe robuste accepté ; PDF/PNG valides acceptés, extension interdite refusée, HTML renommé `.pdf` refusé. **Les 7 passent.**
- Suite complète : **34 tests, 31 succès**, strictement les 3 mêmes échecs préexistants (rapprochement documentaire), aucune régression.

**Non traité et pourquoi**
- **M-4** (champ `Person.password` en clair + `LoginForm`) : la suppression du champ impose une **migration de schéma**, or l'arbre de travail porte déjà une migration en attente et des modifications de modèles non committées. Mêler une migration de sécurité à ce contexte est risqué. `LoginForm` reste un import mort non routé (aucune vuln active). À traiter dans un arbre propre, après inspection du contenu de la table `kyc_person` en production.
- **F-1** (`@require_POST` sur logout) : la déconnexion est déclenchée par des liens **GET** (`<a href="/logout">`) dans une dizaine de templates, dont la navigation active. Forcer le POST casserait la déconnexion partout ; la conversion en formulaires POST est un chantier UI à mener séparément. Sévérité faible (nuisance, aucun gain attaquant) : non appliqué pour ne pas dégrader le fonctionnel.
- **M-6, E-1, F-3** : décisions d'exploitation ou config de déploiement, hors modification de code applicatif isolée.

---

## Limites de l'audit

- Audit **statique uniquement** : aucun test d'intrusion, aucune exploitation réelle des vulnérabilités décrites. Les scénarios d'exploitation sont déduits de la lecture du code et devraient être confirmés en environnement de recette.
- Le contenu de la base de production n'a pas été inspecté (notamment la table `kyc_person` pour M-4, ni les comptes existants et leurs organes).
- La configuration du reverse proxy / serveur web de production (Nginx, IIS) n'a pas été fournie : les conclusions de E-2 sur l'exposition de `/media/` doivent y être recoupées.
- Les scripts R (`Script_V3.r`, `Script_prod.r`, `import_kyc.R`) et les scripts Python racine (`create_users.py`, `delete_user.py`, `import_*.py`) n'ont pas été audités en profondeur ; ils s'exécutent hors du contexte web mais manipulent les mêmes données.
- Les dépendances n'ont pas pu faire l'objet d'un scan automatisé fiable, `requirements.txt` étant inexploitable (M-5). Seule la version de Django a été vérifiée à l'exécution.
