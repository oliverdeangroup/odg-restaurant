from django.core.management.base import BaseCommand

from core.updater import build_package


class Command(BaseCommand):
    help = "Build an update ZIP to upload in Dashboard → Updates."

    def add_arguments(self, parser):
        parser.add_argument("version", help="New version number, e.g. 1.1.0")
        parser.add_argument("--notes", default="", help="Short description of what changed")

    def handle(self, version, notes, **opts):
        path = build_package(version, notes)
        self.stdout.write(self.style.SUCCESS(f"Update package written to {path}"))
