"""POS business rules, shared by the dashboards, the website and the demo."""
from collections import OrderedDict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.utils import notify

from .models import (
    LiveState, Order, OrderItem, Payment, PosSettings, Reservation, Station, Table, money,
)


# ------------------------------------------------------------------ live sync

def bump():
    """Tells every open dashboard that something changed."""
    if not LiveState.objects.filter(pk=1).update(version=F("version") + 1):
        LiveState.objects.get_or_create(pk=1)


def version():
    v = LiveState.objects.filter(pk=1).values_list("version", flat=True).first()
    return v or 0


# ------------------------------------------------------------------ orders

def order_code(table_number, when=None):
    """YYYYMMDDHH + table number, digits only (a digit is added if the table opens twice in one hour)."""
    t = timezone.localtime(when or timezone.now())
    base = f"{t:%Y%m%d%H}{int(table_number)}"
    code, n = base, 2
    while Order.objects.filter(code=code).exists():
        code = f"{base}{n}"
        n += 1
    return code


def open_order(table, waiter, guests=2, customer=None, reservation=None):
    existing = table.open_order
    if existing:
        return existing
    if reservation is None:
        now = timezone.now()
        reservation = Reservation.objects.filter(
            table=table, status__in=(Reservation.Status.CONFIRMED, Reservation.Status.PENDING),
            start__gte=now - timedelta(hours=2), start__lte=now + timedelta(hours=1),
        ).order_by("start").first()
    if reservation is not None:
        customer = customer or reservation.customer
        if reservation.status != Reservation.Status.SEATED:
            reservation.status = Reservation.Status.SEATED
            reservation.save(update_fields=["status"])
    order = Order.objects.create(
        code=order_code(table.number), table=table, table_number=table.number, waiter=waiter,
        guests=max(1, int(guests or 1)), customer=customer, reservation=reservation,
    )
    bump()
    return order


def add_items(order, lines, user):
    """lines: [{"product": Product, "qty": 1, "guest": 1, "options": [...], "notes": ""}]

    Items go straight to the bar or the kitchen. Items without preparation are
    ready for the waiter at once.
    """
    if not lines:
        return []
    batch = (order.items.order_by("-batch").values_list("batch", flat=True).first() or 0) + 1
    now = timezone.now()
    created = []
    for ln in lines:
        p = ln["product"]
        station = p.resolved_station
        it = OrderItem(
            order=order, product=p, name=p.name, category_name=p.category.path, station=station,
            guest_no=max(0, int(ln.get("guest") or 0)), qty=max(1, int(ln.get("qty") or 1)), unit_price=p.price,
            options=ln.get("options") or [], notes=(ln.get("notes") or "")[:255], batch=batch,
            est_minutes=p.prep_minutes, submitted_at=now, added_by=user,
        )
        if station == Station.NONE:
            it.status, it.ready_at, it.est_minutes = OrderItem.Status.READY, now, 0
        created.append(it)
    OrderItem.objects.bulk_create(created)
    if order.status == Order.Status.BILLING:
        order.status = Order.Status.OPEN
        order.save(update_fields=["status"])
    guests_used = max((it.guest_no for it in created), default=0)
    if guests_used > order.guests:
        order.guests = guests_used
        order.save(update_fields=["guests"])
    bump()
    return created


def mark_ready(items, user):
    """Bartender / chef marks items as Completed → the waiter is notified."""
    now = timezone.now()
    items = [i for i in items if i.status in (OrderItem.Status.QUEUED, OrderItem.Status.PREPARING)]
    if not items:
        return 0
    OrderItem.objects.filter(pk__in=[i.pk for i in items]).update(
        status=OrderItem.Status.READY, ready_at=now, prepared_by=user)
    by_order = OrderedDict()
    for i in items:
        by_order.setdefault(i.order_id, []).append(i)
    for oid, its in by_order.items():
        order = its[0].order
        if order.waiter_id:
            names = ", ".join(f"{i.qty}× {i.name}" for i in its)[:200]
            notify([order.waiter], "Table {0}: ready to pick up", message=names,
                   link=f"/dashboard/pos/order/{order.table_id}/", category="pickup",
                   args=(order.table_number,), email=False)
    bump()
    return len(items)


def mark_started(items):
    OrderItem.objects.filter(pk__in=[i.pk for i in items], status=OrderItem.Status.QUEUED).update(
        status=OrderItem.Status.PREPARING, started_at=timezone.now())
    bump()


def mark_served(items, user):
    n = OrderItem.objects.filter(pk__in=[i.pk for i in items], status=OrderItem.Status.READY).update(
        status=OrderItem.Status.SERVED, served_at=timezone.now(), served_by=user)
    if n:
        bump()
    return n


def void_items(items, user, reason=""):
    n = OrderItem.objects.filter(pk__in=[i.pk for i in items], paid=False).exclude(
        status=OrderItem.Status.VOID).update(status=OrderItem.Status.VOID, void_reason=(reason or "")[:255])
    if n:
        bump()
    return n


# ------------------------------------------------------------------ totals

def calc(items, discount=0, s=None):
    """Amounts for a set of items (whole table or one guest)."""
    s = s or PosSettings.load()
    subtotal = money(sum((i.unit_price * i.qty for i in items), Decimal("0")))
    discount = min(money(discount), subtotal) if discount else Decimal("0.00")
    after = subtotal - discount
    service = money(after * s.service_charge_percent / 100)
    base = after + service
    rate = s.tax_rate
    if s.prices_include_tax:
        tax = money(base * rate / (100 + rate))
        total = base
    else:
        tax = money(base * rate / 100)
        total = base + tax
    return {"subtotal": subtotal, "discount": discount, "service": service, "tax": tax, "rate": rate,
            "total": money(total), "net": money(total - tax)}


def bill_groups(order):
    """Unpaid and paid items per guest (Guest #0 = shared by the table)."""
    groups = OrderedDict()
    for it in order.live_items().order_by("guest_no", "submitted_at", "id"):
        groups.setdefault(it.guest_no, []).append(it)
    return groups


def next_bill_number():
    with transaction.atomic():
        s = PosSettings.objects.select_for_update().get(pk=PosSettings.load().pk)
        n = s.next_bill_number
        s.next_bill_number = n + 1
        s.save(update_fields=["next_bill_number"])
    return f"{s.bill_prefix}{n:06d}"


@transaction.atomic
def pay(order, user, method, guest_no=None, tip=0, received=0, discount=0):
    """Checkout for the whole table (guest_no=None) or one guest. Returns the Payment."""
    s = PosSettings.load()
    qs = order.live_items().filter(paid=False)
    if guest_no is not None:
        qs = qs.filter(guest_no=guest_no)
    items = list(qs)
    if not items:
        raise ValueError("Nothing left to pay.")
    t = calc(items, discount, s)
    tip = max(money(tip), Decimal("0.00"))
    received = money(received) if method == Payment.Method.CASH else t["total"] + tip
    if method == Payment.Method.CASH and received < t["total"] + tip:
        received = t["total"] + tip
    payment = Payment.objects.create(
        order=order, guest_no=guest_no, method=method, subtotal=t["subtotal"], discount=t["discount"],
        service_charge=t["service"], amount=t["total"], tax_amount=t["tax"], tip=tip, received=received,
        change=money(received - t["total"] - tip), bill_number=next_bill_number(), received_by=user,
    )
    OrderItem.objects.filter(pk__in=[i.pk for i in items]).update(paid=True)
    if not order.live_items().filter(paid=False).exists():
        close_order(order, user, s)
    bump()
    return payment


def close_order(order, user, s=None):
    s = s or PosSettings.load()
    pays = list(order.payments.all())
    order.subtotal = money(sum((p.subtotal for p in pays), Decimal("0")))
    order.discount = money(sum((p.discount for p in pays), Decimal("0")))
    order.service_charge = money(sum((p.service_charge for p in pays), Decimal("0")))
    order.tax_amount = money(sum((p.tax_amount for p in pays), Decimal("0")))
    order.tip = money(sum((p.tip for p in pays), Decimal("0")))
    order.total = money(sum((p.amount for p in pays), Decimal("0")))
    order.tax_rate = s.tax_rate
    order.bill_number = pays[0].bill_number if len(pays) == 1 else f"{pays[0].bill_number}…{pays[-1].bill_number}" if pays else ""
    order.status = Order.Status.PAID
    order.closed_at = timezone.now()
    order.paid_by = user
    order.save()
    # Anything still waiting in the kitchen/bar is treated as served.
    order.items.filter(status__in=(OrderItem.Status.READY,)).update(status=OrderItem.Status.SERVED, served_at=timezone.now())
    if order.reservation_id:
        Reservation.objects.filter(pk=order.reservation_id).update(status=Reservation.Status.COMPLETED)


def void_order(order, user, reason):
    if order.payments.exists():
        raise ValueError("This order already has payments and cannot be cancelled.")
    order.items.exclude(status=OrderItem.Status.VOID).update(status=OrderItem.Status.VOID, void_reason=reason[:255])
    order.status = Order.Status.VOID
    order.void_reason = reason[:255]
    order.closed_at = timezone.now()
    order.paid_by = user
    order.save()
    if order.reservation_id:
        Reservation.objects.filter(pk=order.reservation_id, status=Reservation.Status.SEATED).update(
            status=Reservation.Status.COMPLETED)
    bump()


# ------------------------------------------------------------------ tables & reservations

def opening_window(day, s=None):
    """(open, close) datetimes for a date, or None when closed. Close may be after midnight."""
    s = s or PosSettings.load()
    hours = s.hours.get(str(day.weekday()))
    if not hours or len(hours) != 2 or not hours[0] or not hours[1]:
        return None
    try:
        o = datetime.combine(day, time.fromisoformat(hours[0]))
        c = datetime.combine(day, time.fromisoformat(hours[1]))
    except ValueError:
        return None
    if c <= o:
        c += timedelta(days=1)
    tz = timezone.get_current_timezone()
    return timezone.make_aware(o, tz), timezone.make_aware(c, tz)


def busy_reservations(start, end, exclude=None):
    qs = Reservation.objects.filter(status__in=Reservation.ACTIVE, start__lt=end,
                                    start__gt=start - timedelta(hours=8)).exclude(table=None)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return [r for r in qs if r.end > start]


def table_is_free(table, start, end, s=None, exclude=None, busy=None, occupied=None):
    """A table is free when no reservation overlaps and it is not occupied
    (a table with an open order stays unavailable until Cassa marks it paid)."""
    s = s or PosSettings.load()
    busy = busy if busy is not None else busy_reservations(start, end, exclude)
    if any(r.table_id == table.pk for r in busy):
        return False
    if occupied is None:
        occupied = set(Order.objects.filter(status__in=Order.OPEN_STATUSES).values_list("table_id", flat=True))
    if table.pk in occupied and start < timezone.now() + timedelta(minutes=s.dining_minutes):
        return False
    return True


def find_table(start, guests, duration=None, online=False, exclude=None, s=None):
    s = s or PosSettings.load()
    end = start + timedelta(minutes=duration or s.dining_minutes)
    tables = Table.objects.filter(active=True, seats__gte=guests).order_by("seats", "number")
    if online:
        tables = tables.filter(online_bookable=True)
    busy = busy_reservations(start, end, exclude)
    occupied = set(Order.objects.filter(status__in=Order.OPEN_STATUSES).values_list("table_id", flat=True))
    for t in tables:
        if table_is_free(t, start, end, s, busy=busy, occupied=occupied):
            return t
    return None


def online_slots(day, guests, s=None):
    """Time slots (every 30 min) that can be booked online for a date."""
    s = s or PosSettings.load()
    win = opening_window(day, s)
    if win is None:
        return []
    open_at, close_at = win
    earliest = timezone.now() + timedelta(hours=s.min_hours_ahead)
    latest_day = timezone.localdate() + timedelta(days=s.max_days_ahead)
    if day > latest_day:
        return []
    out = []
    t = open_at
    last = close_at - timedelta(minutes=s.dining_minutes)
    while t <= last:
        if t >= earliest:
            out.append({"time": timezone.localtime(t).strftime("%H:%M"), "free": find_table(t, guests, online=True, s=s) is not None})
        t += timedelta(minutes=s.slot_minutes)
    return out


def table_states(s=None):
    """Live status of every table for the floor views."""
    s = s or PosSettings.load()
    now = timezone.now()
    orders = {o.table_id: o for o in Order.objects.filter(status__in=Order.OPEN_STATUSES).select_related("waiter")}
    counts = {}
    for it in OrderItem.objects.filter(order__status__in=Order.OPEN_STATUSES).exclude(
            status__in=(OrderItem.Status.VOID,)).values("order__table_id", "status", "station"):
        c = counts.setdefault(it["order__table_id"], {"queued": 0, "ready": 0, "served": 0, "bar": 0, "kitchen": 0})
        if it["status"] in (OrderItem.Status.QUEUED, OrderItem.Status.PREPARING):
            c["queued"] += 1
            if it["station"] in ("bar", "kitchen"):
                c[it["station"]] += 1
        elif it["status"] == OrderItem.Status.READY:
            c["ready"] += 1
        elif it["status"] == OrderItem.Status.SERVED:
            c["served"] += 1
    today = timezone.localdate()
    win = opening_window(today, s)
    day_start = win[0] if win else timezone.make_aware(datetime.combine(today, time(0)))
    day_end = win[1] if win else day_start + timedelta(days=1)
    span = max((day_end - day_start).total_seconds(), 1)
    res_by_table = {}
    for r in Reservation.objects.filter(start__gte=day_start - timedelta(hours=3), start__lt=day_end).exclude(
            status__in=(Reservation.Status.CANCELLED, Reservation.Status.NO_SHOW)).select_related("customer"):
        if r.table_id:
            left = max(0, (r.start - day_start).total_seconds() / span * 100)
            width = max(2, min(100 - left, r.duration_minutes * 60 / span * 100))
            res_by_table.setdefault(r.table_id, []).append({"r": r, "left": round(left, 2), "width": round(width, 2)})
    now_pct = round(min(100, max(0, (now - day_start).total_seconds() / span * 100)), 2)
    out = []
    for t in Table.objects.filter(active=True).select_related("section"):
        o = orders.get(t.pk)
        c = counts.get(t.pk, {"queued": 0, "ready": 0, "served": 0, "bar": 0, "kitchen": 0})
        upcoming = None
        for entry in res_by_table.get(t.pk, []):
            r = entry["r"]
            if r.status in (Reservation.Status.CONFIRMED, Reservation.Status.PENDING) and \
                    now - timedelta(minutes=s.no_show_minutes) <= r.start <= now + timedelta(minutes=60):
                upcoming = r
                break
        if o is not None:
            state = "billing" if o.status == Order.Status.BILLING else ("ready" if c["ready"] else "busy")
        elif upcoming is not None:
            state = "reserved"
        else:
            state = "free"
        out.append({"t": t, "order": o, "state": state, "c": c, "upcoming": upcoming,
                    "timeline": res_by_table.get(t.pk, [])})
    return out, now_pct
