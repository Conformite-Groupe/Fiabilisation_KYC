

1. Lancer le serveur manuellement

python manage.py runserver

2. Lancer Tailwind CSS en developpement uniquement

python manage.py tailwind start

3. Lancer les taches cron pour prechauffe /quality /non_anomalies /dashboard /ppe /comptes_specifiques (TOUS LES JOURS a 6h du matin)

python manage.py warm_ui_caches --users 20 --rules 20

   Variante RAPIDE (6 workers paralleles, sans les modales /non_anom) :
   powershell -ExecutionPolicy Bypass -File .\scripts\warm_ui_caches_fast.ps1

3.bis TAUX QUALITE du dashboard : desormais INTEGRE a warm_ui_caches (etape 3).
   La commande remplit la table TauxQualite (par scope) AVANT de prechauffer les
   dashboards -> plus aucun scan de Kyc_pp (1,1 M) a l'affichage. Rien a lancer en
   plus : le warm_ui_caches du matin s'en charge.

   Commande standalone optionnelle (recalcul complet du taux qualite seul,
   tous les utilisateurs actifs, sans prechauffage) :
   python manage.py compute_quality_rates

   Depuis juillet 2026, compute_quality_rates historise DEUX taux par scope :
   - stock (toute la base, comportement historique)
   - flux  (clients dont DATOUV tombe dans la fenetre configuree dans
     l'admin Django > Configuration flux qualite : veille ou mois precedent)
   L'historique est conserve 400 jours (option --prune-days) pour etudier
   l'evolution, comme les taux de completude dans TauxEvolution.
   Prerequis : DATOUV au format ISO -> normalisation via
   python manage.py normalize_daterev   (traite DATEREV + DATOUV)


4. Vider le cache 
python manage.py shell -c "from django.core.cache import cache; cache.clear()"  --(ne pqs oublier de decommenter qu nivequ des vues correspondqntes)


5. Screening KYC ID — worker OCR des lots charges (Phase 1)
   Traite la file d'attente OCR (documents 'pending' + jobs OCR). A lancer en boucle
   sur le serveur, ou en cron rapproche.
   - Passage unique (cron toutes les 2-5 min) :
       python manage.py process_document_ocr
   - Boucle continue (service) :
       python manage.py process_document_ocr --loop --interval 5 --workers 3

6. Screening KYC ID — purge des anciens jobs (Phase 4, ex. hebdomadaire)
   python manage.py purge_document_jobs --days 30