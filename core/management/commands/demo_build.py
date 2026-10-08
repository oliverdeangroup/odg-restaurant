from django.core.management.base import BaseCommand

from core import demo


class Command(BaseCommand):
    help = "(Re)build the public demo restaurant template and remove expired demo copies."

    def handle(self, *args, **opts):
        demo.cleanup()
        if demo.build_template():
            self.stdout.write(self.style.SUCCESS(f"Demo template ready in {demo.template_dir()}"))
        else:
            self.stdout.write("Another process is building the demo template right now.")
