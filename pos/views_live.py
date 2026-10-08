"""Live POS screens: waiter, bar, kitchen, overview and the live floor.

Every live screen has parts marked `data-live-src`; `pos/live.js` polls
`live_state` and re-loads those parts (`?partial=1`) when the version changes.
"""
import json
from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, F, Q, Sum
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.i18n import _
from core.models import Notification
from core.permissions import can, require
from core.utils import log_activity

from . import services
from .models import Category, Customer, Order, OrderItem, PosSettings, Product, Reservation, Section, Station, Table


def _partial(request):
    return request.GET.get("partial") == "1"


# ------------------------------------------------------------------ polling

@require("home")
def live_state(request):
    """Tiny JSON the dashboards poll: the change counter + new notifications."""
    try:
        after = int(request.GET.get("n") or 0)
    except ValueError:
        after = 0
    notes = []
    qs = Notification.objects.filter(recipient=request.user, is_read=False)
    if after:
        notes = [{"id": n.pk, "title": n.title, "message": n.message, "link": n.link, "category": n.category}
                 for n in qs.filter(pk__gt=after).order_by("pk")[:10]]
    last = Notification.objects.filter(recipient=request.user).order_by("-pk").values_list("pk", flat=True).first() or 0
    return JsonResponse({"v": services.version(), "notes": notes, "last": last, "unread": qs.count()})


# ------------------------------------------------------------------ floor (all roles)

def floor_ctx():
    s = PosSettings.load()
    states, now_pct = services.table_states(s)
    return {"states": states, "sections": Section.objects.all(), "s": s, "now_pct": now_pct,
            "legend": [("free", _("Free")), ("reserved", _("Reserved")), ("busy", _("Occupied")),
                       ("ready", _("Ready to serve")), ("billing", _("Bill requested"))]}


@require("floor")
def floor(request):
    ctx = floor_ctx()
    ctx["can_order"] = can(request.user, "pos_waiter")
    ctx["can_design"] = can(request.user, "floor_design")
    if _partial(request):
        return render(request, "pos/_floor.html", ctx)
    return render(request, "pos/floor.html", ctx)


# ------------------------------------------------------------------ waiter

@require("pos_waiter")
def tables(request):
    """Waiter start screen: the floor + my open tables + items to pick up."""
    ctx = floor_ctx()
    ctx["can_order"] = True
    mine = Order.objects.filter(status__in=Order.OPEN_STATUSES)
    if request.user.role == "waiter":
        mine = mine.filter(waiter=request.user)
    ctx["my_orders"] = mine.select_related("table").annotate(
        ready=Count("items", filter=Q(items__status=OrderItem.Status.READY)),
        waiting=Count("items", filter=Q(items__status__in=(OrderItem.Status.QUEUED, OrderItem.Status.PREPARING))),
    ).order_by("table_number")
    ctx["pickup"] = OrderItem.objects.filter(status=OrderItem.Status.READY, order__in=mine).select_related("order").order_by("ready_at")
    if _partial(request):
        return render(request, "pos/_tables.html", ctx)
    return render(request, "pos/tables.html", ctx)


def _menu_json():
    cats = list(Category.objects.filter(active=True).values("id", "parent_id", "name", "station", "order"))
    prods = []
    for p in Product.objects.filter(active=True, category__active=True).select_related("category__parent__parent__parent"):
        prods.append({"id": p.pk, "c": p.category_id, "n": p.name, "p": str(p.price), "st": p.resolved_station,
                      "o": p.options, "a": p.available, "code": p.code, "d": p.description, "m": p.prep_minutes})
    return {"cats": cats, "prods": prods}


@require("pos_waiter")
def order_screen(request, table_id):
    table = get_object_or_404(Table, pk=table_id, active=True)
    order = table.open_order
    s = PosSettings.load()
    if order is None:
        now = timezone.now()
        res = Reservation.objects.filter(
            table=table, status__in=(Reservation.Status.CONFIRMED, Reservation.Status.PENDING),
            start__gte=now - timedelta(hours=2), start__lte=now + timedelta(hours=1)).select_related("customer").first()
        if request.method == "POST":
            customer = None
            if request.POST.get("customer"):
                customer = Customer.objects.filter(pk=request.POST["customer"]).first()
            order = services.open_order(table, request.user, request.POST.get("guests") or 2, customer,
                                        res if request.POST.get("use_reservation") else None)
            log_activity(request, "create", f"Table {table.number} opened (order {order.code})", "pos")
            return redirect("pos:order", table.pk)
        return render(request, "pos/open_table.html", {"table": table, "reservation": res, "s": s})
    if _partial(request):
        return render(request, "pos/_order_items.html", _order_ctx(request, order))
    ctx = _order_ctx(request, order)
    ctx.update({"table": table, "menu_json": _menu_json(), "s": s, "tables": Table.objects.filter(active=True)})
    return render(request, "pos/order.html", ctx)


def _order_ctx(request, order):
    groups = services.bill_groups(order)
    items = [it for its in groups.values() for it in its]
    return {
        "order": order, "groups": groups, "totals": services.calc(items),
        "ready_count": sum(1 for i in items if i.status == OrderItem.Status.READY),
        "can_cassa": can(request.user, "cassa_pay"),
        "can_void_any": can(request.user, "cassa_pay"),
    }


def _get_open(order_id):
    order = get_object_or_404(Order, pk=order_id)
    if not order.is_open:
        raise Http404
    return order


@require("pos_waiter")
@require_POST
def order_submit(request, order_id):
    """Receives the waiter's new items (JSON) and sends them to bar and kitchen."""
    order = _get_open(order_id)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return HttpResponseBadRequest("Bad JSON")
    raw = data.get("lines") or []
    if not isinstance(raw, list) or len(raw) > 200:
        return HttpResponseBadRequest("Bad lines")
    products = {p.pk: p for p in Product.objects.filter(pk__in=[ln.get("product") for ln in raw if isinstance(ln, dict)],
                                                         active=True).select_related("category")}
    lines, errors = [], []
    for ln in raw:
        p = products.get(ln.get("product")) if isinstance(ln, dict) else None
        if p is None:
            continue
        if not p.available:
            errors.append(_("{0} is sold out.").format(p.name))
            continue
        chosen = ln.get("options") or {}
        opts = []
        for g in p.options:
            val = chosen.get(g["name"]) if isinstance(chosen, dict) else None
            if val in g["choices"]:
                opts.append(f"{g['name']}: {val}")
            elif g["required"]:
                errors.append(_("Choose {0} for {1}.").format(g["name"], p.name))
        try:
            qty, guest = min(max(int(ln.get("qty") or 1), 1), 99), min(max(int(ln.get("guest") or 0), 0), 99)
        except (TypeError, ValueError):
            qty, guest = 1, 0
        lines.append({"product": p, "qty": qty, "guest": guest, "options": opts, "notes": str(ln.get("notes") or "")[:255]})
    if errors:
        return JsonResponse({"ok": False, "error": " ".join(errors)}, status=400)
    created = services.add_items(order, lines, request.user)
    bar = sum(1 for i in created if i.station == Station.BAR)
    kitchen = sum(1 for i in created if i.station == Station.KITCHEN)
    log_activity(request, "create", f"Order {order.code}: {len(created)} items submitted", "pos")
    return JsonResponse({"ok": True, "count": len(created), "bar": bar, "kitchen": kitchen})


@require("pos_waiter")
@require_POST
def items_action(request, order_id):
    """Served / cancel for one or more items of an open order."""
    order = _get_open(order_id)
    ids = [int(x) for x in request.POST.getlist("item") if x.isdigit()]
    action = request.POST.get("action")
    items = list(order.items.filter(pk__in=ids)) if ids else []
    if action == "serve_all":
        items = list(order.items.filter(status=OrderItem.Status.READY))
        action = "serve"
    if action == "serve":
        services.mark_served(items, request.user)
        Notification.objects.filter(recipient=request.user, category="pickup", is_read=False,
                                    link=f"/dashboard/pos/order/{order.table_id}/").update(is_read=True)
    elif action == "void":
        if not can(request.user, "cassa_pay"):
            # Waiters may only cancel what the kitchen/bar has not started yet.
            items = [i for i in items if i.status == OrderItem.Status.QUEUED]
        n = services.void_items(items, request.user, request.POST.get("reason", ""))
        if n:
            log_activity(request, "delete", f"Order {order.code}: {n} items cancelled", "pos")
    elif action == "guests":
        try:
            order.guests = min(max(int(request.POST.get("guests") or 1), 1), 99)
            order.save(update_fields=["guests"])
            services.bump()
        except ValueError:
            pass
    elif action == "bill":
        order.status = Order.Status.BILLING
        order.save(update_fields=["status"])
        services.bump()
        messages.success(request, _("The bill was requested. The manager sees it in Cassa."))
    elif action == "move":
        target = Table.objects.filter(pk=request.POST.get("table"), active=True).first()
        if target and target.open_order is None:
            old = order.table_number
            order.table, order.table_number = target, target.number
            order.save(update_fields=["table", "table_number"])
            services.bump()
            log_activity(request, "update", f"Order {order.code} moved from table {old} to {target.number}", "pos")
            messages.success(request, _("Moved to table {0}.").format(target.number))
            return redirect("pos:order", target.pk)
        messages.error(request, _("That table is not free."))
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": True})
    return redirect("pos:order", order.table_id)


# ------------------------------------------------------------------ bar & kitchen

def _tickets(station):
    s = PosSettings.load()
    now = timezone.now()
    items = OrderItem.objects.filter(
        station=station, status__in=(OrderItem.Status.QUEUED, OrderItem.Status.PREPARING),
        order__status__in=Order.OPEN_STATUSES).select_related("order__waiter").order_by("submitted_at", "id")
    tickets = {}
    for it in items:
        key = (it.order_id, it.batch)
        t = tickets.get(key)
        if t is None:
            t = tickets[key] = {"order": it.order, "batch": it.batch, "items": [], "submitted": it.submitted_at,
                                "est": 0, "guests": set()}
        t["items"].append(it)
        t["est"] = max(t["est"], it.est_minutes)
        t["guests"].add(it.guest_no)
    out = []
    for t in tickets.values():
        t["due"] = t["submitted"] + timedelta(minutes=t["est"])
        late = (now - t["due"]).total_seconds() / 60
        t["state"] = "late" if late > s.late_after_minutes else ("due" if late > 0 else "ok")
        t["guests"] = sorted(t["guests"])
        out.append(t)
    return out


def _station_stats(station):
    today = timezone.localdate()
    done = OrderItem.objects.filter(station=station, ready_at__date=today)
    secs = [i.prep_seconds for i in done.only("ready_at", "submitted_at") if i.prep_seconds is not None]
    return {
        "done_today": done.count(),
        "avg_minutes": round(sum(secs) / len(secs) / 60, 1) if secs else None,
    }


def _station(request, station, template_title):
    tickets = _tickets(station)
    recent = OrderItem.objects.filter(station=station, status=OrderItem.Status.READY,
                                      ready_at__gte=timezone.now() - timedelta(minutes=10)).select_related("order").order_by("-ready_at")[:12]
    ctx = {"station": station, "tickets": tickets, "recent": recent, "stats": _station_stats(station),
           "waiting": sum(len(t["items"]) for t in tickets), "title": template_title,
           "can_act": can(request.user, "pos_bar" if station == Station.BAR else "pos_kitchen")}
    if _partial(request):
        return render(request, "pos/_queue.html", ctx)
    return render(request, "pos/queue.html", ctx)


@require("pos_bar")
def bar(request):
    return _station(request, Station.BAR, _("Bar"))


@require("pos_kitchen")
def kitchen(request):
    return _station(request, Station.KITCHEN, _("Kitchen"))


@require("pos_bar", "pos_kitchen")
@require_POST
def station_action(request, station):
    if station not in (Station.BAR, Station.KITCHEN):
        raise Http404
    if not can(request.user, "pos_bar" if station == Station.BAR else "pos_kitchen"):
        raise PermissionDenied
    ids = [int(x) for x in request.POST.getlist("item") if x.isdigit()]
    items = list(OrderItem.objects.filter(pk__in=ids, station=station).select_related("order"))
    action = request.POST.get("action")
    if action == "done":
        services.mark_ready(items, request.user)
    elif action == "start":
        services.mark_started(items)
    elif action == "undo":
        OrderItem.objects.filter(pk__in=[i.pk for i in items], status=OrderItem.Status.READY,
                                 order__status__in=Order.OPEN_STATUSES).update(
            status=OrderItem.Status.QUEUED, ready_at=None, prepared_by=None)
        services.bump()
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": True})
    return redirect("pos:bar" if station == Station.BAR else "pos:kitchen")


# ------------------------------------------------------------------ overview

def overview_ctx():
    s = PosSettings.load()
    now = timezone.now()
    today = timezone.localdate()
    orders = list(Order.objects.filter(status__in=Order.OPEN_STATUSES).select_related("waiter", "customer").annotate(
        n_wait=Count("items", filter=Q(items__status__in=(OrderItem.Status.QUEUED, OrderItem.Status.PREPARING))),
        n_ready=Count("items", filter=Q(items__status=OrderItem.Status.READY)),
        n_served=Count("items", filter=Q(items__status=OrderItem.Status.SERVED)),
        amount=Sum(F("items__unit_price") * F("items__qty"), filter=~Q(items__status=OrderItem.Status.VOID)),
    ).order_by("table_number"))
    late = 0
    for st in (Station.BAR, Station.KITCHEN):
        late += sum(1 for t in _tickets(st) if t["state"] == "late")
    paid = Order.objects.filter(status=Order.Status.PAID, closed_at__date=today)
    stats = {
        "open": len(orders),
        "guests": sum(o.guests for o in orders),
        "bar": OrderItem.objects.filter(station=Station.BAR, status__in=(OrderItem.Status.QUEUED, OrderItem.Status.PREPARING), order__status__in=Order.OPEN_STATUSES).count(),
        "kitchen": OrderItem.objects.filter(station=Station.KITCHEN, status__in=(OrderItem.Status.QUEUED, OrderItem.Status.PREPARING), order__status__in=Order.OPEN_STATUSES).count(),
        "ready": OrderItem.objects.filter(status=OrderItem.Status.READY, order__status__in=Order.OPEN_STATUSES).count(),
        "late": late,
        "sales": paid.aggregate(t=Sum("total"))["t"] or 0,
        "paid_count": paid.count(),
        "reservations": Reservation.objects.filter(start__date=today, status__in=Reservation.ACTIVE).count(),
    }
    upcoming = Reservation.objects.filter(start__gte=now - timedelta(minutes=s.no_show_minutes), start__date=today,
                                          status__in=(Reservation.Status.CONFIRMED, Reservation.Status.PENDING)).select_related("customer", "table")[:8]
    return {"orders": orders, "stats": stats, "upcoming": upcoming, "s": s}


@require("pos_overview")
def overview(request):
    ctx = overview_ctx()
    if _partial(request):
        return render(request, "pos/_overview.html", ctx)
    return render(request, "pos/overview.html", ctx)
