"""
Crée (ou met à jour) les comptes testeurs à partir du fichier Testeurs.xlsx.

Colonnes attendues :
    First_name | username et email | Mot de passe | Téléphone | Filiale | Organe | Code_expl | Agence

Idempotent : l'utilisateur est identifié par son username (= email). À chaque exécution
les champs de profil et le mot de passe sont réalignés sur le fichier.

    python manage.py create_testeurs                     # fichier Testeurs.xlsx à la racine
    python manage.py create_testeurs --file autre.xlsx   # autre chemin
    python manage.py create_testeurs --force-change       # impose le changement de MDP au 1er login

Par défaut force_password_change=False : le mot de passe fourni fonctionne directement
(pratique pour des comptes de test partagés).
"""
import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model


COLS = ("First_name", "email", "password", "telephone", "filiale", "organe", "code_expl", "agence")


class Command(BaseCommand):
    help = "Crée / met à jour les comptes testeurs depuis Testeurs.xlsx."

    def add_arguments(self, parser):
        parser.add_argument("--file", default="Testeurs.xlsx",
                            help="Chemin du fichier Excel (défaut : Testeurs.xlsx).")
        parser.add_argument("--force-change", action="store_true",
                            help="Impose le changement de mot de passe au 1er login.")

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError("openpyxl est requis (pip install openpyxl).")

        path = options["file"]
        if not os.path.exists(path):
            raise CommandError(f"Fichier introuvable : {path}")

        force_change = options["force_change"]
        User = get_user_model()

        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))

        created = updated = skipped = 0
        for raw in rows[1:]:                   
            data = {COLS[i]: (raw[i] if i < len(raw) else None) for i in range(len(COLS))}
            email = (str(data["email"]).strip() if data["email"] else "")
            password = (str(data["password"]).strip() if data["password"] else "")
            if not email or not password:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"  [SKIP] ligne sans email/mot de passe : {raw}"))
                continue

            def clean(v):
                return str(v).strip() if v is not None else ""

            defaults = {
                "email": email,
                "first_name": clean(data["First_name"]),
                "filiale": clean(data["filiale"]),
                "organe": clean(data["organe"]),
                "code_expl": clean(data["code_expl"]),
                "agence": clean(data["agence"]),
                "téléphone": clean(data["telephone"]),
                "force_password_change": force_change,
            }

            user, is_created = User.objects.get_or_create(
                username=email, defaults=defaults)
            if not is_created:
                for k, v in defaults.items():
                    setattr(user, k, v)
            user.set_password(password)
            user.save()

            created += int(is_created)
            updated += int(not is_created)
            tag = "NEW" if is_created else "UPD"
            self.stdout.write(f"  [{tag}] {email:28} {defaults['filiale']:8} {defaults['organe']}")

        self.stdout.write(self.style.SUCCESS(
            f"Terminé : {created} créé(s), {updated} mis à jour, {skipped} ignoré(s). "
            f"force_password_change={force_change}."))
