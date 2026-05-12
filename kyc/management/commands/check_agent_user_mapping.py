from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import connection


class Command(BaseCommand):
    help = "Check correspondance Agents -> Users avant migration (email/username/code_expl)."

    def handle(self, *args, **options):
        user_model = get_user_model()
        user_table = user_model._meta.db_table
        agent_table = "kyc_agents"

        with connection.cursor() as cursor:
            tables = connection.introspection.table_names()
            if agent_table not in tables:
                self.stderr.write(
                    self.style.ERROR(
                        f"Table '{agent_table}' introuvable. Tables disponibles: {', '.join(tables)}"
                    )
                )
                return

            # Total agents
            cursor.execute(f"SELECT COUNT(*) FROM {agent_table}")
            total_agents = cursor.fetchone()[0]

            # Matched by email/username
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM {agent_table} a
                JOIN {user_table} u
                  ON LOWER(a.email) = LOWER(u.username)
                  OR LOWER(a.email) = LOWER(u.email)
                """
            )
            matched_email = cursor.fetchone()[0]

            # Matched by code_expl
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM {agent_table} a
                JOIN {user_table} u
                  ON a.expl = u.code_expl
                """
            )
            matched_code = cursor.fetchone()[0]

            # Unmatched (by email/username or code_expl)
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM {agent_table} a
                WHERE NOT EXISTS (
                    SELECT 1 FROM {user_table} u
                    WHERE LOWER(a.email) = LOWER(u.username)
                       OR LOWER(a.email) = LOWER(u.email)
                       OR a.expl = u.code_expl
                )
                """
            )
            unmatched = cursor.fetchone()[0]

        self.stdout.write(self.style.SUCCESS("=== CHECK AGENTS -> USERS ==="))
        self.stdout.write(f"Total agents          : {total_agents}")
        self.stdout.write(f"Matched by email/user : {matched_email}")
        self.stdout.write(f"Matched by code_expl  : {matched_code}")
        self.stdout.write(f"Unmatched             : {unmatched}")
        self.stdout.write("")
        self.stdout.write("Si 'Unmatched' > 0, ils pointeront vers le user placeholder.")
