"""Restaurant operations: products, floor, customers, reservations, orders, Cassa.

Real-time: every change calls `live.bump()`; dashboards poll a tiny endpoint
and re-load their live parts when the version number changes.

Records are never hard-deleted once money is involved: paid orders, payments
and bills stay in the database (Curaçao requires 10 years of bookkeeping).
The order *history screen* shows the last 90 days (Settings → POS).
"""
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import Singleton

User = settings.AUTH_USER_MODEL
CENT = Decimal("0.01")


def money(v):
    return Decimal(v or 0).quantize(CENT, rounding=ROUND_HALF_UP)


class Station(models.TextChoices):
    BAR = "bar", "Bar"
    KITCHEN = "kitchen", "Kitchen"
    NONE = "none", "No preparation"


BILL_FORMATS = [("80mm", "Receipt 80 mm"), ("a5", "A5"), ("a4", "A4")]


class PosSettings(Singleton):
    # Money
    currency_code = models.CharField(max_length=5, default="XCG", help_text="XCG = Caribbean guilder (Curaçao since 31-03-2025)")
    currency_symbol = models.CharField(max_length=5, default="Cg")
    tax_name = models.CharField(max_length=20, default="OB", help_text="Omzetbelasting (Curaçao sales tax)")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("6.00"), help_text="Percent. Check the current rate with your accountant.")
    prices_include_tax = models.BooleanField(default=True, help_text="Menu prices already include OB")
    service_charge_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"), help_text="0 = no service charge")
    tip_suggestions = models.CharField(max_length=40, default="10,15,20", help_text="Tip buttons in Cassa, in percent")
    # Bills
    default_bill_format = models.CharField(max_length=5, choices=BILL_FORMATS, default="80mm")
    bill_prefix = models.CharField(max_length=10, blank=True, default="", help_text="Optional text before the bill number")
    next_bill_number = models.PositiveIntegerField(default=1, help_text="Bills are numbered without gaps")
    bill_header_text = models.CharField(max_length=200, blank=True)
    bill_footer_text = models.CharField(max_length=200, blank=True, default="Thank you for your visit! · Masha danki!")
    crib_number = models.CharField("CRIB number", max_length=30, blank=True, help_text="Tax number, printed on bills and reports")
    kvk_number = models.CharField("Chamber of Commerce (KvK) number", max_length=30, blank=True)
    # Live POS
    order_history_days = models.PositiveSmallIntegerField(default=90, help_text="Days shown in Order history")
    manager_history_days = models.PositiveSmallIntegerField(default=7, help_text="Managers see this many days of history")
    live_refresh_seconds = models.PositiveSmallIntegerField(default=3)
    late_after_minutes = models.PositiveSmallIntegerField(default=5, help_text="A ticket turns red this many minutes after its estimated time")
    sound_alerts = models.BooleanField(default=True)
    waiter_can_discount = models.BooleanField(default=False)
    # Floor
    floor_width = models.PositiveIntegerField(default=1200)
    floor_height = models.PositiveIntegerField(default=760)
    grid_size = models.PositiveSmallIntegerField(default=20)
    # Reservations
    online_reservations = models.BooleanField(default=True)
    slot_minutes = models.PositiveSmallIntegerField(default=30)
    dining_minutes = models.PositiveSmallIntegerField(default=90, help_text="How long a table is kept for one reservation")
    min_hours_ahead = models.PositiveSmallIntegerField(default=2, help_text="Online reservations must be made at least this many hours in advance")
    max_days_ahead = models.PositiveSmallIntegerField(default=60)
    max_guests_online = models.PositiveSmallIntegerField(default=10)
    auto_confirm = models.BooleanField(default=True, help_text="Online reservations are confirmed right away when a table is free")
    no_show_minutes = models.PositiveSmallIntegerField(default=20, help_text="A table is released this long after the reservation time when the guest has not arrived")
    opening_hours = models.JSONField(default=dict, blank=True, help_text="Per weekday (0 = Monday): [open, close]")

    def __str__(self):
        return "POS settings"

    DEFAULT_HOURS = {str(d): ["12:00", "22:00"] for d in range(7)}

    @property
    def hours(self):
        return self.opening_hours or self.DEFAULT_HOURS

    @property
    def tips(self):
        out = []
        for p in self.tip_suggestions.split(","):
            try:
                out.append(int(p.strip()))
            except ValueError:
                pass
        return out

    def fmt(self, amount):
        return f"{self.currency_symbol} {money(amount):,.2f}"


# ------------------------------------------------------------------ menu

class Category(models.Model):
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    name = models.CharField(max_length=80)
    station = models.CharField(max_length=10, choices=Station.choices, blank=True,
                               help_text="Where items are prepared. Empty = same as the parent category.")
    order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)
    show_on_website = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.path

    def ancestors(self):
        out, c, seen = [], self, set()
        while c is not None and c.pk not in seen:
            seen.add(c.pk)
            out.append(c)
            c = c.parent
        return list(reversed(out))

    @property
    def path(self):
        return " → ".join(c.name for c in self.ancestors())

    @property
    def resolved_station(self):
        for c in reversed(self.ancestors()):
            if c.station:
                return c.station
        return Station.KITCHEN

    @property
    def depth(self):
        return len(self.ancestors()) - 1


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, blank=True, help_text="Optional short code / PLU")
    description = models.CharField(max_length=300, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="public/products/", blank=True)
    station = models.CharField(max_length=10, choices=Station.choices, blank=True, help_text="Empty = use the category")
    prep_minutes = models.PositiveSmallIntegerField(default=10, help_text="Estimated preparation time")
    options_text = models.TextField(
        "Preparation options", blank=True,
        help_text="One group per line: Name: choice | choice. Start with * when the waiter must choose. "
                  "Example: *Doneness: Rare | Medium rare | Medium | Well done",
    )
    active = models.BooleanField(default=True)
    available = models.BooleanField(default=True, help_text="Untick when sold out today")
    show_on_website = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    @property
    def resolved_station(self):
        return self.station or self.category.resolved_station

    @property
    def options(self):
        """[{"name": "Doneness", "choices": [...], "required": True}, ...]"""
        groups = []
        for line in self.options_text.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            name, choices = line.split(":", 1)
            required = name.startswith("*")
            name = name.lstrip("*").strip()
            choices = [c.strip() for c in choices.split("|") if c.strip()]
            if name and choices:
                groups.append({"name": name, "choices": choices, "required": required})
        return groups


# ------------------------------------------------------------------ floor

class Section(models.Model):
    name = models.CharField(max_length=60)
    color = models.CharField(max_length=7, default="#e9eef8")
    x = models.IntegerField(default=20)
    y = models.IntegerField(default=20)
    w = models.PositiveIntegerField(default=560)
    h = models.PositiveIntegerField(default=700)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class Table(models.Model):
    class Shape(models.TextChoices):
        RECT = "rect", "Rectangle"
        ROUND = "round", "Round"

    number = models.PositiveIntegerField(unique=True)
    label = models.CharField(max_length=30, blank=True, help_text="Optional name, e.g. Terrace 1")
    section = models.ForeignKey(Section, null=True, blank=True, on_delete=models.SET_NULL, related_name="tables")
    shape = models.CharField(max_length=6, choices=Shape.choices, default=Shape.RECT)
    seats = models.PositiveSmallIntegerField(default=4)
    x = models.IntegerField(default=40)
    y = models.IntegerField(default=40)
    w = models.PositiveIntegerField(default=90)
    h = models.PositiveIntegerField(default=90)
    rotation = models.SmallIntegerField(default=0)
    active = models.BooleanField(default=True)
    online_bookable = models.BooleanField(default=True, help_text="Can be booked on the website")

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"#{self.number}" + (f" {self.label}" if self.label else "")

    @property
    def open_order(self):
        return self.orders.filter(status__in=Order.OPEN_STATUSES).order_by("-opened_at").first()


# ------------------------------------------------------------------ customers

class Customer(models.Model):
    number = models.PositiveIntegerField(unique=True, editable=False)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField("Phone / WhatsApp", max_length=40, blank=True)
    whatsapp = models.BooleanField("Reachable on WhatsApp", default=True)
    notes = models.TextField(blank=True, help_text="Allergies, preferences, birthdays …")
    marketing = models.BooleanField("Wants news and offers", default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def code(self):
        """Unique customer ID, e.g. C000042."""
        return f"C{self.number:06d}"

    def save(self, *args, **kwargs):
        if not self.number:
            last = Customer.objects.aggregate(m=models.Max("number"))["m"] or 0
            self.number = last + 1
        super().save(*args, **kwargs)


class Reservation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        SEATED = "seated", "Seated"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No-show"

    class Source(models.TextChoices):
        PHONE = "phone", "Phone"
        WEBSITE = "website", "Website"
        WALK_IN = "walk_in", "Walk-in"
        STAFF = "staff", "Staff"

    ACTIVE = (Status.PENDING, Status.CONFIRMED, Status.SEATED)

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="reservations")
    table = models.ForeignKey(Table, null=True, blank=True, on_delete=models.SET_NULL, related_name="reservations")
    start = models.DateTimeField(db_index=True)
    duration_minutes = models.PositiveSmallIntegerField(default=90)
    guests = models.PositiveSmallIntegerField(default=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.PHONE)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["start"]

    def __str__(self):
        return f"{self.customer} · {timezone.localtime(self.start):%d-%m %H:%M}"

    @property
    def end(self):
        return self.start + timedelta(minutes=self.duration_minutes)


# ------------------------------------------------------------------ orders

class Order(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        BILLING = "billing", "Bill requested"
        PAID = "paid", "Paid"
        VOID = "void", "Cancelled"

    OPEN_STATUSES = (Status.OPEN, Status.BILLING)

    code = models.CharField(max_length=24, unique=True, help_text="YYYYMMDDHH + table number, digits only")
    table = models.ForeignKey(Table, null=True, on_delete=models.SET_NULL, related_name="orders")
    table_number = models.PositiveIntegerField()
    waiter = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    reservation = models.ForeignKey(Reservation, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    guests = models.PositiveSmallIntegerField(default=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    note = models.CharField(max_length=255, blank=True)
    opened_at = models.DateTimeField(default=timezone.now, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # Filled in at checkout
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tip = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Amount paid, without tip")
    bill_number = models.CharField(max_length=30, blank=True, db_index=True)
    paid_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self):
        return self.code

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    def live_items(self):
        return self.items.exclude(status=OrderItem.Status.VOID)


class OrderItem(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Waiting"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Completed"
        SERVED = "served", "Served"
        VOID = "void", "Cancelled"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    name = models.CharField(max_length=120)
    category_name = models.CharField(max_length=200, blank=True)
    station = models.CharField(max_length=10, choices=Station.choices, default=Station.KITCHEN, db_index=True)
    guest_no = models.PositiveSmallIntegerField(default=1, help_text="0 = shared by the table")
    qty = models.PositiveSmallIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    options = models.JSONField(default=list, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    batch = models.PositiveSmallIntegerField(default=1, help_text="Submission round within the order")
    est_minutes = models.PositiveSmallIntegerField(default=10)
    paid = models.BooleanField(default=False, help_text="Paid in a split bill")
    submitted_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    served_at = models.DateTimeField(null=True, blank=True)
    added_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    prepared_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    served_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["submitted_at", "id"]

    def __str__(self):
        return f"{self.qty}× {self.name}"

    @property
    def line_total(self):
        return money(self.unit_price * self.qty)

    @property
    def due_at(self):
        return self.submitted_at + timedelta(minutes=self.est_minutes)

    @property
    def prep_seconds(self):
        if self.ready_at and self.submitted_at:
            return int((self.ready_at - self.submitted_at).total_seconds())
        return None


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    guest_no = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Empty = the whole table")
    method = models.CharField(max_length=5, choices=Method.choices)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Bill amount incl. OB, without tip")
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tip = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    received = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    change = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bill_number = models.CharField(max_length=30)
    paid_at = models.DateTimeField(default=timezone.now, db_index=True)
    received_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["paid_at"]


class Bill(models.Model):
    """A saved PDF bill (pro-forma or receipt)."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="bills")
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.PROTECT, related_name="bills")
    guest_no = models.PositiveSmallIntegerField(null=True, blank=True)
    number = models.CharField(max_length=30, blank=True)
    is_receipt = models.BooleanField(default=False, help_text="False = pro-forma bill before payment")
    fmt = models.CharField(max_length=5, choices=BILL_FORMATS, default="80mm")
    file = models.FileField(upload_to="private/bills/%Y/%m/")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


class DayClose(models.Model):
    """End-of-day cash count (Z report)."""

    date = models.DateField(unique=True)
    opening_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    counted_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    card_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sales_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tips_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.CharField(max_length=255, blank=True)
    closed_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    closed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-date"]

    @property
    def difference(self):
        return money(self.counted_cash - self.expected_cash)


class LiveState(Singleton):
    """One number that goes up on every POS change; dashboards poll it."""

    version = models.BigIntegerField(default=1)
