"""The public demo must be isolated: from the real restaurant and between visitors."""
import json
import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from core import demo
from core.models import DemoSandbox, SystemSettings
from pos.models import Order, OrderItem, Product, Table


class _DefaultPlusDemoCopies(frozenset):
    """Transactions only wrap 'default', but connections to demo copies are allowed."""

    def __contains__(self, alias):
        return alias == "default" or str(alias).startswith("demo_")


class DemoTests(TestCase):
    @classmethod
    def _validate_databases(cls):
        return _DefaultPlusDemoCopies({"default"})

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.mkdtemp()
        cls.override = override_settings(DATA_DIR=Path(cls.tmp))
        cls.override.enable()
        demo.build_template()

    @classmethod
    def tearDownClass(cls):
        cls.override.disable()
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        SystemSettings.objects.update_or_create(pk=1, defaults={"demo_enabled": True})

    def _start(self, client, role, ip):
        r = client.post(f"/demo/start/{role}/", REMOTE_ADDR=ip)
        self.assertEqual(r.status_code, 302)
        r = client.get(r["Location"], REMOTE_ADDR=ip)
        self.assertEqual(r.status_code, 302)
        return r["Location"]

    def test_demo_roles_and_isolation(self):
        self.assertEqual(self.client.get("/demo/").status_code, 200)
        start = self._start(self.client, "waiter", "203.0.113.5")
        self.assertEqual(start, "/dashboard/pos/")
        r = self.client.get(start)
        self.assertContains(r, "Ready to pick up")
        sb = DemoSandbox.objects.get(ip="203.0.113.5")
        # Take an order on a free table inside the demo
        with demo.use(demo.sandbox_dir(sb.code)):
            table = Table.objects.exclude(orders__status__in=Order.OPEN_STATUSES).first()
            pid = Product.objects.get(name="Cola Zero").pk
            open_before = Order.objects.filter(status__in=Order.OPEN_STATUSES).count()
        self.client.post(f"/dashboard/pos/order/{table.pk}/", {"guests": 2})
        with demo.use(demo.sandbox_dir(sb.code)):
            order = Order.objects.get(table_id=table.pk, status="open")
            self.assertEqual(Order.objects.filter(status__in=Order.OPEN_STATUSES).count(), open_before + 1)
        r = self.client.post(f"/dashboard/pos/order/{order.pk}/submit/", json.dumps({"lines": [{"product": pid, "qty": 1, "guest": 1}]}),
                             content_type="application/json")
        self.assertTrue(r.json()["ok"])
        # Switch role to bartender and owner
        self.client.get("/dashboard/demo/enter/?as=bartender")
        self.assertEqual(self.client.get("/dashboard/pos/bar/").status_code, 200)
        self.client.get("/dashboard/demo/enter/?as=owner")
        self.assertEqual(self.client.get("/dashboard/finance/").status_code, 200)
        # The administrator dashboard is not in the demo
        self.assertEqual(self.client.get("/dashboard/demo/enter/?as=admin").status_code, 302)
        self.assertEqual(self.client.get("/dashboard/settings/").status_code, 403)
        # The real database has no orders at all
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        # A second visitor gets a separate copy without the first visitor's order
        other = self.client_class()
        self._start(other, "chef", "198.51.100.7")
        sb2 = DemoSandbox.objects.exclude(pk=sb.pk).get()
        with demo.use(demo.sandbox_dir(sb2.code)):
            self.assertFalse(Order.objects.filter(table_id=table.pk, status="open").exists())
        self.assertEqual(other.get("/dashboard/pos/kitchen/").status_code, 200)

    def test_demo_times_are_current(self):
        self._start(self.client, "manager", "203.0.113.9")
        sb = DemoSandbox.objects.get()
        from django.utils import timezone

        with demo.use(demo.sandbox_dir(sb.code)):
            latest = Order.objects.filter(status__in=Order.OPEN_STATUSES).order_by("-opened_at").first()
            self.assertLess((timezone.now() - latest.opened_at).total_seconds(), 3600)
            self.assertTrue(all(o.code.isdigit() for o in Order.objects.all()[:50]))

    def test_demo_restaurant_website_is_synced(self):
        from datetime import timedelta

        from django.utils import timezone

        from pos.models import Reservation

        r = self.client.get("/demo/site/", REMOTE_ADDR="203.0.113.20")
        self.assertEqual(r.status_code, 302)  # a private copy is made first
        r = self.client.get("/demo/site/", REMOTE_ADDR="203.0.113.20")
        self.assertContains(r, "Dinosaur BBQ")
        self.assertContains(r, 'href="/demo/site/menu/"')
        self.assertContains(r, 'action="/demo/site/book/"')
        self.assertContains(r, "noindex")
        self.assertContains(self.client.get("/demo/site/menu/"), "Smoked brisket")
        sb = DemoSandbox.objects.get(ip="203.0.113.20")
        day = (timezone.localdate() + timedelta(days=3)).isoformat()
        slots = self.client.get(f"/demo/site/book/slots/?date={day}&guests=2").json()["slots"]
        free = next(s for s in slots if s["free"])
        r = self.client.post("/demo/site/book/", {"date": day, "time": free["time"], "guests": 2, "first_name": "Demo",
                                                    "last_name": "Visitor", "email": "visitor@example.com"})
        self.assertTrue(r.json()["ok"])
        with demo.use(demo.sandbox_dir(sb.code)):
            self.assertTrue(Reservation.objects.filter(customer__email="visitor@example.com").exists())
        self.assertFalse(Reservation.objects.exists())  # the real restaurant is not touched
        # The same visitor sees it in the demo dashboard
        self.client.get("/dashboard/demo/enter/?as=manager")
        self.assertContains(self.client.get(f"/dashboard/pos/reservations/?date={day}"), "Visitor")
