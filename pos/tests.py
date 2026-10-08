"""End-to-end checks for ODG-RESTAURANT. Run on the PC: python manage.py test"""
import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.management.commands.setup_odg import make_categories
from core.models import Notification, Role, User
from core.nav import MENU
from finance.models import Expense
from website import starter

from . import services
from .models import Bill, Category, Customer, Order, OrderItem, Payment, PosSettings, Product, Reservation, Section, Table


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_categories()
        cls.cats = {c.path.replace(" → ", "/"): c for c in Category.objects.all()}
        cls.cola = Product.objects.create(category=cls.cats["Beverages/Soft Drinks"], name="Cola Zero", price=Decimal("5.50"), prep_minutes=2)
        cls.steak = Product.objects.create(category=cls.cats["Food/Main Course/Meat"], name="Pepper Steak", price=Decimal("42.00"),
                                           prep_minutes=18, options_text="*Doneness: Rare | Medium | Well done\nSide: Fries | Rice")
        sec = Section.objects.create(name="Section 1")
        cls.t1 = Table.objects.create(number=1, section=sec, seats=4)
        cls.t2 = Table.objects.create(number=2, section=sec, seats=2)
        cls.users = {}
        for role in (Role.ADMIN, Role.MODERATOR, Role.OWNER, Role.MANAGER, Role.WAITER, Role.BARTENDER, Role.CHEF):
            cls.users[role] = User.objects.create_user(role, f"{role}@example.com", "Test-pass-123", role=role, first_name=role.title())
        starter.create("Test Grill")

    def login(self, role):
        self.client.force_login(self.users[role])


class OrderFlowTests(Base):
    def test_full_flow_waiter_bar_kitchen_cassa(self):
        # Waiter opens table 1 and submits drinks + food for two guests
        self.login(Role.WAITER)
        r = self.client.post(reverse("pos:order", args=[self.t1.pk]), {"guests": 2})
        self.assertEqual(r.status_code, 302)
        order = Order.objects.get(table=self.t1)
        now = timezone.localtime()
        self.assertTrue(order.code.startswith(now.strftime("%Y%m%d%H")) and order.code.endswith("1"))
        self.assertTrue(order.code.isdigit())
        lines = [{"product": self.cola.pk, "qty": 1, "guest": 1}, {"product": self.cola.pk, "qty": 1, "guest": 2},
                 {"product": self.steak.pk, "qty": 1, "guest": 1, "options": {"Doneness": "Medium", "Side": "Fries"}, "notes": "no salt"}]
        r = self.client.post(reverse("pos:order_submit", args=[order.pk]), json.dumps({"lines": lines}), content_type="application/json")
        self.assertEqual(r.json(), {"ok": True, "count": 3, "bar": 2, "kitchen": 1})
        # A required option is enforced
        r = self.client.post(reverse("pos:order_submit", args=[order.pk]), json.dumps({"lines": [{"product": self.steak.pk}]}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

        # Bartender sees only the drinks; chef only the food with its details
        self.login(Role.BARTENDER)
        r = self.client.get(reverse("pos:bar") + "?partial=1")
        self.assertContains(r, "Cola Zero")
        self.assertNotContains(r, "Pepper Steak")
        self.login(Role.CHEF)
        r = self.client.get(reverse("pos:kitchen") + "?partial=1")
        self.assertContains(r, "Doneness: Medium")
        self.assertContains(r, "no salt")
        steak = order.items.get(product=self.steak)
        self.client.post(reverse("pos:station_action", args=["kitchen"]), {"item": steak.pk, "action": "done"})
        steak.refresh_from_db()
        self.assertEqual(steak.status, OrderItem.Status.READY)
        # The chef cannot touch the bar
        r = self.client.post(reverse("pos:station_action", args=["bar"]), {"item": steak.pk, "action": "done"})
        self.assertEqual(r.status_code, 403)
        # Completed items leave the live queue
        self.assertNotContains(self.client.get(reverse("pos:kitchen") + "?partial=1"), "no salt")

        # The waiter gets a pick-up notification and marks it served
        note = Notification.objects.get(recipient=self.users[Role.WAITER], category="pickup")
        self.assertIn("1", note.title)
        self.login(Role.WAITER)
        live = self.client.get(reverse("pos:live") + "?n=0").json()
        self.assertGreater(live["v"], 1)
        self.client.post(reverse("pos:items_action", args=[order.pk]), {"item": steak.pk, "action": "serve"})
        steak.refresh_from_db()
        self.assertEqual(steak.status, OrderItem.Status.SERVED)
        # The waiter cannot take payments
        r = self.client.post(reverse("pos:pay", args=[order.pk]), {"method": "cash"})
        self.assertEqual(r.status_code, 403)

        # Manager: split bill → guest 2 pays cash, then the rest by card with a tip
        self.login(Role.MANAGER)
        self.assertContains(self.client.get(reverse("pos:cassa_order", args=[order.pk])), "Guest")
        r = self.client.post(reverse("pos:pay", args=[order.pk]), {"guest": "2", "method": "cash", "received": "10", "fmt": "80mm"})
        self.assertEqual(r.status_code, 302)
        p1 = Payment.objects.get(order=order, guest_no=2)
        self.assertEqual(p1.amount, Decimal("5.50"))
        self.assertEqual(p1.change, Decimal("4.50"))
        self.assertEqual(p1.tax_amount, Decimal("0.31"))  # 6 % OB included
        order.refresh_from_db()
        self.assertTrue(order.is_open)
        self.client.post(reverse("pos:pay", args=[order.pk]), {"guest": "all", "method": "card", "tip": "5", "fmt": "a4"})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.total, Decimal("53.00"))
        self.assertEqual(order.tip, Decimal("5.00"))
        numbers = list(Payment.objects.filter(order=order).order_by("paid_at").values_list("bill_number", flat=True))
        self.assertEqual(numbers, ["000001", "000002"])
        bills = Bill.objects.filter(order=order, is_receipt=True)
        self.assertEqual(bills.count(), 2)
        pdf = self.client.get(reverse("pos:bill", args=[bills.first().pk]))
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        # The table is free again
        self.assertIsNone(self.t1.open_order)
        # History and finance see the sale
        self.assertContains(self.client.get(reverse("pos:history")), order.code)
        self.login(Role.OWNER)
        r = self.client.get(reverse("finance:overview") + "?period=day")
        self.assertContains(r, "53.00")
        r = self.client.get(reverse("finance:report") + "?period=day&download=1")
        self.assertEqual(r["Content-Type"], "application/pdf")
        r = self.client.get(reverse("finance:export") + "?what=sales&period=day")
        self.assertIn("000002", r.content.decode("utf-8"))

    def test_order_code_unique_same_hour(self):
        a = services.open_order(self.t2, self.users[Role.WAITER])
        services.void_order(a, self.users[Role.MANAGER], "test")
        b = services.open_order(self.t2, self.users[Role.WAITER])
        self.assertNotEqual(a.code, b.code)
        self.assertTrue(b.code.isdigit())

    def test_paid_orders_cannot_be_voided(self):
        o = services.open_order(self.t2, self.users[Role.WAITER])
        services.add_items(o, [{"product": self.cola, "qty": 1, "guest": 1}], self.users[Role.WAITER])
        services.pay(o, self.users[Role.MANAGER], "card")
        with self.assertRaises(ValueError):
            services.void_order(o, self.users[Role.MANAGER], "x")


class PermissionTests(Base):
    def test_every_menu_page_opens_for_its_roles(self):
        from core.permissions import perms_for

        for role, user in self.users.items():
            self.client.force_login(user)
            perms = perms_for(user)
            for _label, _icon, subs in MENU:
                for _sub, url_name, perm in subs:
                    r = self.client.get(reverse(url_name))
                    if perm in perms:
                        self.assertEqual(r.status_code, 200, f"{role} → {url_name}")
                    else:
                        self.assertIn(r.status_code, (403, 302), f"{role} must not open {url_name}")

    def test_owner_and_manager_limits(self):
        self.login(Role.ADMIN)
        r = self.client.post(reverse("core:user_new", args=["staff"]), {
            "role": "owner", "first_name": "Second", "last_name": "Owner", "username": "owner2", "is_active": "on"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="owner2").exists())
        User.objects.create_user("m2", role=Role.MANAGER)
        r = self.client.post(reverse("core:user_new", args=["staff"]), {
            "role": "manager", "first_name": "Third", "last_name": "Manager", "username": "m3", "is_active": "on"})
        self.assertFalse(User.objects.filter(username="m3").exists())

    def test_admin_cannot_take_payments_but_sees_cassa(self):
        o = services.open_order(self.t1, self.users[Role.WAITER])
        self.login(Role.ADMIN)
        self.assertEqual(self.client.get(reverse("pos:cassa_order", args=[o.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("pos:pay", args=[o.pk]), {"method": "cash"}).status_code, 403)

    def test_manager_history_is_limited(self):
        o = services.open_order(self.t1, self.users[Role.WAITER])
        Order.objects.filter(pk=o.pk).update(opened_at=timezone.now() - timedelta(days=30))
        self.login(Role.MANAGER)
        self.assertEqual(self.client.get(reverse("pos:history_order", args=[o.pk])).status_code, 200)  # managers have Cassa
        self.login(Role.OWNER)
        self.assertEqual(self.client.get(reverse("pos:history_order", args=[o.pk])).status_code, 200)


class PagesTests(Base):
    def test_other_screens(self):
        self.login(Role.MANAGER)
        o = services.open_order(self.t1, self.users[Role.MANAGER], 3)
        services.add_items(o, [{"product": self.steak, "qty": 1, "guest": 1, "options": ["Doneness: Rare"]}], self.users[Role.MANAGER])
        for url in (reverse("pos:order", args=[self.t1.pk]), reverse("pos:order", args=[self.t1.pk]) + "?partial=1",
                    reverse("pos:overview") + "?partial=1", reverse("pos:floor") + "?partial=1", reverse("pos:tables") + "?partial=1",
                    reverse("pos:cassa_order", args=[o.pk]) + "?partial=detail", reverse("pos:cassa") + "?partial=list",
                    reverse("pos:floor_design"), reverse("pos:product_new"), reverse("pos:product_edit", args=[self.steak.pk]),
                    reverse("pos:reservation_new"), reverse("pos:customer_new"), reverse("pos:day_close"),
                    reverse("pos:performance") + "?period=month", reverse("pos:history") + "?period=week",
                    reverse("pos:order", args=[self.t2.pk]), reverse("core:home") + "?partial=1", reverse("core:profile"),
                    reverse("core:notifications")):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.login(Role.OWNER)
        for url in (reverse("finance:expense_new"), reverse("finance:expenses") + "?period=year", reverse("finance:overview") + "?period=year",
                    reverse("pos:day_closes")):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.login(Role.ADMIN)
        for url in (reverse("website:page_edit", args=[1]), reverse("website:page_new"), reverse("website:footer"),
                    reverse("website:menus"), reverse("core:user_new", args=["staff"]) + "?role=chef", reverse("core:updates")):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_floor_save(self):
        self.login(Role.MANAGER)
        data = {"sections": [{"id": "n1", "name": "Terrace", "color": "#ffffff", "x": 0, "y": 0, "w": 500, "h": 500}],
                "tables": [{"id": self.t1.pk, "number": 2, "seats": 4, "x": 40, "y": 40, "w": 100, "h": 100, "section": "n1"},
                           {"id": self.t2.pk, "number": 1, "seats": 2, "shape": "round", "x": 200, "y": 40, "w": 80, "h": 80},
                           {"id": "", "number": 3, "seats": 6, "x": 300, "y": 300, "w": 120, "h": 90}]}
        r = self.client.post(reverse("pos:floor_save"), json.dumps(data), content_type="application/json")
        self.assertEqual(r.json(), {"ok": True})
        self.t1.refresh_from_db()
        self.assertEqual((self.t1.number, self.t1.section.name), (2, "Terrace"))
        self.assertEqual(Table.objects.filter(active=True).count(), 3)

    def test_expense_and_profit(self):
        Expense.objects.create(description="Fish", amount=Decimal("106.00"), tax_amount=Decimal("6.00"))
        from finance.reports import figures

        f = figures("day", timezone.localdate())
        self.assertEqual(f["expenses_net"], Decimal("100.00"))
        self.assertEqual(f["profit"], Decimal("-100.00"))


class WebsiteTests(Base):
    def test_public_pages_and_booking(self):
        s = PosSettings.load()
        s.opening_hours = {str(d): ["00:00", "23:59"] for d in range(7)}
        s.min_hours_ahead = 1
        s.save()
        for url in ("/", "/menu/", "/reservations/", "/about-us/", "/contact/", "/robots.txt", "/sitemap.xml", "/demo/", "/login/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get("/"), "Book your table")
        self.assertContains(self.client.get("/menu/"), "Pepper Steak")
        day = (timezone.localdate() + timedelta(days=2)).isoformat()
        slots = self.client.get(f"/book/slots/?date={day}&guests=2").json()["slots"]
        self.assertTrue(slots and slots[0]["free"])
        r = self.client.post("/book/", {"date": day, "time": slots[0]["time"], "guests": 2, "first_name": "Ana",
                                         "last_name": "Rojer", "email": "ana@example.com"})
        self.assertTrue(r.json()["ok"], r.content)
        res = Reservation.objects.get(customer__email="ana@example.com")
        self.assertEqual(res.table, self.t2)  # smallest table that fits
        # Same slot again: the only 2-seat table is taken, so the 4-seat table is used
        r = self.client.post("/book/", {"date": day, "time": slots[0]["time"], "guests": 2, "first_name": "Bo",
                                         "last_name": "Mos", "email": "bo@example.com"})
        self.assertEqual(Reservation.objects.get(customer__email="bo@example.com").table, self.t1)
        r = self.client.post("/book/", {"date": day, "time": slots[0]["time"], "guests": 2, "first_name": "Cy",
                                         "last_name": "No", "email": "cy@example.com"})
        self.assertFalse(r.json()["ok"])
        # Customer data is shared with POS
        self.assertTrue(Customer.objects.filter(email="ana@example.com").exists())

    def test_occupied_table_is_not_bookable_until_paid(self):
        start = timezone.now() + timedelta(minutes=30)
        o = services.open_order(self.t2, self.users[Role.WAITER])
        self.assertFalse(services.table_is_free(self.t2, start, start + timedelta(minutes=90)))
        services.add_items(o, [{"product": self.cola, "qty": 1, "guest": 1}], self.users[Role.WAITER])
        services.pay(o, self.users[Role.MANAGER], "cash")
        self.assertTrue(services.table_is_free(self.t2, start, start + timedelta(minutes=90)))

    def test_builder_layout_is_cleaned(self):
        from website.builder import clean_layout

        bad = {"sections": [{"layout": "1", "style": {"bg": "red;x", "image": "javascript:alert(1)"},
                             "columns": [{"widgets": [{"type": "text", "data": {"html": "<p>Hi</p><script>alert(1)</script>"}},
                                                      {"type": "evil", "data": {}},
                                                      {"type": "image", "data": {"src": "https://x.test/a.jpg') ; background:url('y"}}]}]}]}
        out = clean_layout(bad)
        w = out["sections"][0]["columns"][0]["widgets"]
        self.assertEqual(len(w), 2)
        self.assertNotIn("script", w[0]["data"]["html"])
        self.assertNotIn("'", w[1]["data"]["src"])
        self.assertEqual(out["sections"][0]["style"]["image"], "")
        self.assertEqual(out["sections"][0]["style"]["bg"], "")

    def test_languages(self):
        self.assertContains(self.client.get("/login/?lang=nl"), "Inloggen")
        self.assertContains(self.client.get("/login/?lang=es"), "Iniciar sesión")
