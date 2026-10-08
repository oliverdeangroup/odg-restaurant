"""First-time setup: settings, product categories, floor sections and a starter website.

    python manage.py setup_odg --admin admin --email you@example.com

Safe to run again: it only adds what is missing and never removes data.
"""
import getpass

from django.core.management.base import BaseCommand

from core.models import Role, SystemSettings, User
from pos.models import Category, PosSettings, Section, Station, Table
from website import starter
from website.models import Appearance, Brand, SEOSettings

# The category structure from the specification.
CATEGORIES = [
    ("Beverages", Station.BAR, [("Soft Drinks", []), ("Alcohol", [("Cocktails", []), ("Beer", []), ("Wine", [])]), ("Coffee & Tea", [])]),
    ("Food", Station.KITCHEN, [("Appetizers", []), ("Main Course", [("Meat", []), ("Fish", []), ("Vegetarian", [])]),
                              ("Side Dish", []), ("Desserts", [])]),
]


def make_categories():
    def add(name, parent, station, kids, order):
        c, _ = Category.objects.get_or_create(name=name, parent=parent, defaults={"station": station or "", "order": order})
        for i, (kname, kkids) in enumerate(kids):
            add(kname, c, None, kkids, i)

    for i, (name, station, kids) in enumerate(CATEGORIES):
        add(name, None, station, kids, i)


class Command(BaseCommand):
    help = "Prepare ODG-RESTAURANT for first use (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--admin", help="Username of the first administrator")
        parser.add_argument("--email", default="")
        parser.add_argument("--password", help="Leave out to be asked (safer)")
        parser.add_argument("--no-website", action="store_true", help="Skip the starter pages and menu")

    def handle(self, *args, **o):
        SystemSettings.load()
        PosSettings.load()
        brand = Brand.load()
        Appearance.load()
        SEOSettings.load()
        if not Category.objects.exists():
            make_categories()
            self.stdout.write("Product categories ready.")
        if not Section.objects.exists() and not Table.objects.exists():
            left = Section.objects.create(name="Section 1", color="#e8f1ea", x=20, y=20, w=560, h=700, order=0)
            right = Section.objects.create(name="Section 2", color="#eaeef8", x=620, y=20, w=560, h=700, order=1)
            n = 1
            for sec, x0 in ((left, 60), (right, 660)):
                for row in range(3):
                    for col in range(2):
                        round_ = n % 3 == 0
                        Table.objects.create(number=n, section=sec, shape="round" if round_ else "rect", seats=2 if round_ else 4,
                                             x=x0 + col * 240, y=80 + row * 220, w=100 if round_ else 110, h=100 if round_ else 90)
                        n += 1
            self.stdout.write("Floor with 2 sections and 12 tables ready (change it in POS > Floor manager).")
        if not o["no_website"] and starter.create(brand.name):
            self.stdout.write("Starter website created.")

        if o["admin"]:
            user = User.objects.filter(username=o["admin"]).first()
            if user:
                self.stdout.write(f"Administrator {user.username} already exists.")
            else:
                pw = o["password"] or getpass.getpass("Password for the administrator: ")
                User.objects.create_superuser(o["admin"], o["email"], pw, role=Role.ADMIN, first_name="Admin")
                self.stdout.write(self.style.SUCCESS(f"Administrator {o['admin']} created."))
        self.stdout.write(self.style.SUCCESS("ODG-RESTAURANT is ready."))
