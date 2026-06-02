from django.core.management.base import BaseCommand

from kyc.completeness import calculate_completeness


class Command(BaseCommand):
    help = "Calcule les taux de completude KYC selon les champs critiques configures."

    def add_arguments(self, parser):
        parser.add_argument("--applicability", choices=["PP", "PM"], help="Limiter le calcul a PP ou PM.")
        parser.add_argument("--filiale", help="Limiter le calcul a une filiale precise, ex: BOA SN.")

    def handle(self, *args, **options):
        created = calculate_completeness(
            applicability=options.get("applicability"),
            filiale=options.get("filiale"),
        )
        self.stdout.write(self.style.SUCCESS(f"Calcul termine: {created} ligne(s) de resultats generee(s)."))
