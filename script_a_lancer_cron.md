

1. Lancer le serveur manuellement

python manage.py runserver

2. Lancer Tailwind CSS en developpement uniquement

python manage.py tailwind start

3. Lancer les taches cron pour prechauffe /quality /non_anomalies /dashboard /ppe /comptes_specifiques (TOUS LES JOURS a 6h du matin)

python manage.py warm_ui_caches --users 20 --rules 20


4. Vider le cache 
python manage.py shell -c "from django.core.cache import cache; cache.clear()"  --(ne pqs oublier de decommenter qu nivequ des vues correspondqntes)