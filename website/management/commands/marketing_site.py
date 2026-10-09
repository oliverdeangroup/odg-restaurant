from django.core.management.base import BaseCommand

from website import marketing


class Command(BaseCommand):
    help = "Put the ODG-RESTAURANT product website in place (replaces only the untouched starter pages)."

    def handle(self, *args, **opts):
        pages = marketing.create()
        self.stdout.write(self.style.SUCCESS(f"Product website ready: {', '.join(p.title for p in pages)}"))
