"""Products, floor designer, reservations, customers, staff performance, POS settings."""
import json
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.i18n import _
from core.models import Role, User
from core.permissions import can, require
from core.utils import log_activity

from . import services
from .forms import CategoryForm, CustomerForm, PosSettingsForm, ProductForm, ReservationForm, ReservationSettingsForm
from .models import Category, Customer, Order, OrderItem, PosSettings, Product, Reservation, Section, Station, Table
from .views_cassa import aware, period_range


# ------------------------------------------------------------------ products

def category_tree():
    cats = list(Category.objects.annotate(n=Count("products")))
    by_parent = {}
    for c in cats:
        by_parent.setdefault(c.parent_id, []).append(c)
    out = []

    def walk(pid, depth):
        for c in by_parent.get(pid, []):
            c.level = depth
            out.append(c)
            walk(c.pk, depth + 1)

    walk(None, 0)
    return out


@require("products")
def products(request):
    tree = category_tree()
    qs = Product.objects.select_related("category__parent__parent")
    cat = request.GET.get("cat")
    if cat and cat.isdigit():
        ids, frontier = {int(cat)}, {int(cat)}
        while frontier:
            frontier = set(Category.objects.filter(parent_id__in=frontier).values_list("pk", flat=True)) - ids
            ids |= frontier
        qs = qs.filter(category_id__in=ids)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__iexact=q) | Q(description__icontains=q))
    cform = CategoryForm(prefix="c")
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "category":
            inst = get_object_or_404(Category, pk=request.POST["pk"]) if request.POST.get("pk") else None
            cform = CategoryForm(request.POST, instance=inst, prefix="c")
            if cform.is_valid():
                c = cform.save()
                services.bump()
                messages.success(request, _("Category {0} saved.").format(c.path))
                return redirect(request.get_full_path())
        elif action == "category_delete":
            c = get_object_or_404(Category, pk=request.POST.get("pk"))
            if c.products.exists() or c.children.exists():
                messages.error(request, _("Move or delete the products and sub-categories first."))
            else:
                c.delete()
                messages.success(request, _("Category deleted."))
            return redirect("pos:products")
        elif action == "toggle":
            p = get_object_or_404(Product, pk=request.POST.get("pk"))
            p.available = not p.available
            p.save(update_fields=["available"])
            services.bump()
            return JsonResponse({"ok": True, "available": p.available}) if request.headers.get("x-requested-with") == "fetch" else redirect(request.get_full_path())
    return render(request, "pos/products.html", {
        "tree": tree, "products": qs.order_by("category__order", "category__name", "order", "name"), "cat": cat, "q": q,
        "cform": cform, "s": PosSettings.load(),
    })


@require("products")
def product_edit(request, pk=None):
    obj = get_object_or_404(Product, pk=pk) if pk else Product()
    if not pk and request.GET.get("cat"):
        obj.category_id = request.GET["cat"]
    form = ProductForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST":
        if request.POST.get("delete") and obj.pk:
            obj.active = False
            obj.save(update_fields=["active"])
            messages.success(request, _("{0} is no longer on the menu (kept for the order history).").format(obj.name))
            services.bump()
            return redirect("pos:products")
        if form.is_valid():
            p = form.save()
            services.bump()
            log_activity(request, "update" if pk else "create", f"Product {p.name} saved", "products")
            messages.success(request, _("{0} was saved.").format(p.name))
            if request.POST.get("again"):
                return redirect(f"/dashboard/pos/products/new/?cat={p.category_id}")
            return redirect(f"/dashboard/pos/products/?cat={p.category_id}")
    return render(request, "pos/product_form.html", {"form": form, "obj": obj, "s": PosSettings.load()})


# ------------------------------------------------------------------ floor designer

@require("floor_design")
def floor_design(request):
    s = PosSettings.load()
    tables = [{"id": t.pk, "number": t.number, "label": t.label, "section": t.section_id, "shape": t.shape, "seats": t.seats,
               "x": t.x, "y": t.y, "w": t.w, "h": t.h, "rotation": t.rotation, "online": t.online_bookable,
               "busy": t.orders.filter(status__in=Order.OPEN_STATUSES).exists()}
              for t in Table.objects.filter(active=True)]
    sections = [{"id": sec.pk, "name": sec.name, "color": sec.color, "x": sec.x, "y": sec.y, "w": sec.w, "h": sec.h}
                for sec in Section.objects.all()]
    return render(request, "pos/floor_design.html", {"s": s, "data": {"tables": tables, "sections": sections,
                                                                         "width": s.floor_width, "height": s.floor_height,
                                                                         "grid": s.grid_size}})


def _int(v, default=0, lo=-10000, hi=10000):
    try:
        return min(max(int(float(v)), lo), hi)
    except (TypeError, ValueError):
        return default


@require("floor_design")
@require_POST
def floor_save(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except ValueError:
        return HttpResponseBadRequest("Bad JSON")
    tables, sections = data.get("tables") or [], data.get("sections") or []
    numbers = [_int(t.get("number"), 0, 0, 99999) for t in tables]
    if any(n <= 0 for n in numbers) or len(set(numbers)) != len(numbers):
        return JsonResponse({"ok": False, "error": _("Every table needs its own number.")}, status=400)
    with transaction.atomic():
        sec_map = {}
        keep_sections = set()
        for i, sd in enumerate(sections):
            sec = Section.objects.filter(pk=sd.get("id")).first() if str(sd.get("id", "")).isdigit() else None
            sec = sec or Section()
            sec.name = str(sd.get("name") or _("Section"))[:60]
            sec.color = str(sd.get("color") or "#e9eef8")[:7]
            sec.x, sec.y = _int(sd.get("x")), _int(sd.get("y"))
            sec.w, sec.h = _int(sd.get("w"), 300, 40, 5000), _int(sd.get("h"), 300, 40, 5000)
            sec.order = i
            sec.save()
            sec_map[str(sd.get("id"))] = sec
            keep_sections.add(sec.pk)
        Section.objects.exclude(pk__in=keep_sections).delete()
        keep = set()
        # Free the numbers first so tables can swap numbers without a clash.
        ids = [t.get("id") for t in tables if str(t.get("id", "")).isdigit()]
        for t in Table.objects.filter(pk__in=ids):
            t.number = 1000000 + t.pk
            t.save(update_fields=["number"])
        for td in tables:
            t = Table.objects.filter(pk=td.get("id")).first() if str(td.get("id", "")).isdigit() else None
            t = t or Table()
            t.number = _int(td.get("number"), 1, 1, 99999)
            t.label = str(td.get("label") or "")[:30]
            t.shape = "round" if td.get("shape") == "round" else "rect"
            t.seats = _int(td.get("seats"), 4, 1, 99)
            t.x, t.y = _int(td.get("x")), _int(td.get("y"))
            t.w, t.h = _int(td.get("w"), 90, 30, 600), _int(td.get("h"), 90, 30, 600)
            t.rotation = _int(td.get("rotation"), 0, -360, 360)
            t.online_bookable = bool(td.get("online", True))
            t.section = sec_map.get(str(td.get("section")))
            t.active = True
            t.save()
            keep.add(t.pk)
        # Removed tables are deactivated (orders and reservations keep their history).
        busy = Table.objects.exclude(pk__in=keep).filter(active=True, orders__status__in=Order.OPEN_STATUSES)
        if busy.exists():
            transaction.set_rollback(True)
            return JsonResponse({"ok": False, "error": _("Table {0} has an open order and cannot be removed.").format(busy.first().number)}, status=400)
        for t in Table.objects.exclude(pk__in=keep).filter(active=True):
            t.active = False
            t.number = 1000000 + t.pk
            t.save(update_fields=["active", "number"])
    services.bump()
    log_activity(request, "update", "Floor layout saved", "floor")
    return JsonResponse({"ok": True})


# ------------------------------------------------------------------ reservations

@require("reservations")
def reservations(request):
    period = request.GET.get("period", "day")
    if period not in ("day", "week", "month"):
        period = "day"
    try:
        ref = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        ref = timezone.localdate()
    start, end = period_range(period, ref)
    qs = Reservation.objects.filter(start__gte=aware(start), start__lt=aware(end)).select_related("customer", "table")
    status = request.GET.get("status")
    if status in Reservation.Status.values:
        qs = qs.filter(status=status)
    elif status != "all":
        qs = qs.exclude(status__in=(Reservation.Status.CANCELLED,))
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(customer__first_name__icontains=q) | Q(customer__last_name__icontains=q)
                       | Q(customer__phone__icontains=q) | Q(customer__email__icontains=q))
    rows = list(qs)
    days = {}
    for r in rows:
        days.setdefault(timezone.localtime(r.start).date(), []).append(r)
    step = {"day": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=31)}[period]
    return render(request, "pos/reservations.html", {
        "days": sorted(days.items()), "count": len(rows), "guests": sum(r.guests for r in rows),
        "period": period, "ref": ref, "start": start, "end": end - timedelta(days=1), "status": status, "q": q,
        "prev": ref - step, "next": ref + step, "statuses": Reservation.Status.choices,
    })


@require("reservations")
def reservation_edit(request, pk=None):
    obj = get_object_or_404(Reservation.objects.select_related("customer"), pk=pk) if pk else Reservation(source=Reservation.Source.PHONE)
    s = PosSettings.load()
    if not pk:
        obj.duration_minutes = s.dining_minutes
    customer = obj.customer if pk else None
    if not pk and request.GET.get("customer"):
        customer = Customer.objects.filter(pk=request.GET["customer"]).first()
    form = ReservationForm(request.POST or None, instance=obj, initial={"date": request.GET.get("date") or timezone.localdate()})
    cform = CustomerForm(request.POST or None, instance=customer, prefix="cu", require_email=False)
    if request.method == "POST":
        existing = Customer.objects.filter(pk=request.POST.get("customer_id")).first() if request.POST.get("customer_id") else None
        if existing is not None:
            cform = CustomerForm(request.POST, instance=existing, prefix="cu", require_email=False)
        if form.is_valid() and cform.is_valid():
            r = form.save(commit=False)
            start = timezone.make_aware(datetime.combine(form.cleaned_data["date"], form.cleaned_data["time"]))
            r.start = start
            if r.table is None:
                r.table = services.find_table(start, r.guests, r.duration_minutes, exclude=obj if pk else None)
                if r.table is None:
                    messages.warning(request, _("No free table for {0} guests at that time. The reservation is saved without a table.").format(r.guests))
            elif not services.table_is_free(r.table, start, start + timedelta(minutes=r.duration_minutes), s, exclude=obj if pk else None):
                messages.warning(request, _("Table {0} is already reserved or occupied at that time. Please check.").format(r.table.number))
            with transaction.atomic():
                r.customer = cform.save()
                if not pk:
                    r.created_by = request.user
                r.save()
            services.bump()
            log_activity(request, "update" if pk else "create", f"Reservation {r} saved", "reservations")
            messages.success(request, _("Reservation saved."))
            return redirect(f"/dashboard/pos/reservations/?date={timezone.localtime(r.start).date()}")
    return render(request, "pos/reservation_form.html", {"form": form, "cform": cform, "obj": obj, "customer": customer, "s": s})


@require("reservations")
@require_POST
def reservation_status(request, pk):
    r = get_object_or_404(Reservation, pk=pk)
    st = request.POST.get("status")
    if st in Reservation.Status.values:
        r.status = st
        r.save(update_fields=["status"])
        services.bump()
        log_activity(request, "update", f"Reservation {r} → {st}", "reservations")
        if st == Reservation.Status.SEATED and r.table_id and r.table.open_order is None and can(request.user, "pos_waiter"):
            services.open_order(r.table, request.user, r.guests, r.customer, r)
            return redirect("pos:order", r.table_id)
    return redirect(request.POST.get("next") or "pos:reservations")


@require("reservations", "customers")
def customer_search(request):
    q = request.GET.get("q", "").strip()
    out = []
    if len(q) >= 2:
        for c in Customer.objects.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
                                         | Q(phone__icontains=q))[:10]:
            out.append({"id": c.pk, "code": c.code, "name": str(c), "email": c.email, "phone": c.phone,
                        "first_name": c.first_name, "last_name": c.last_name, "notes": c.notes, "whatsapp": c.whatsapp})
    return JsonResponse({"results": out})


# ------------------------------------------------------------------ customers

@require("customers")
def customers(request):
    qs = Customer.objects.annotate(n_res=Count("reservations", distinct=True), n_orders=Count("orders", distinct=True))
    q = request.GET.get("q", "").strip()
    if q:
        cond = Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q)
        digits = q.upper().lstrip("C")
        if digits.isdigit():
            cond |= Q(number=int(digits))
        qs = qs.filter(cond)
    page = Paginator(qs.order_by("last_name", "first_name"), 40).get_page(request.GET.get("page"))
    return render(request, "pos/customers.html", {"page": page, "q": q})


@require("customers")
def customer_edit(request, pk=None):
    obj = get_object_or_404(Customer, pk=pk) if pk else Customer()
    form = CustomerForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        c = form.save()
        services.bump()
        log_activity(request, "update" if pk else "create", f"Customer {c.code} {c} saved", "customers")
        messages.success(request, _("{0} was saved.").format(c))
        return redirect("pos:customer", c.pk)
    ctx = {"form": form, "obj": obj}
    if obj.pk:
        orders = obj.orders.order_by("-opened_at")
        ctx.update({
            "reservations": obj.reservations.select_related("table").order_by("-start")[:50],
            "orders": orders[:50],
            "tables": obj.orders.values("table_number").annotate(n=Count("id")).order_by("-n")[:10],
            "spent": orders.filter(status=Order.Status.PAID).aggregate(t=Sum("total"))["t"] or 0,
            "visits": orders.filter(status=Order.Status.PAID).count(),
            "s": PosSettings.load(),
        })
    return render(request, "pos/customer.html", ctx)


# ------------------------------------------------------------------ staff performance

@require("performance")
def performance(request):
    period = request.GET.get("period", "day")
    if period not in ("day", "week", "month"):
        period = "day"
    try:
        ref = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        ref = timezone.localdate()
    start, end = period_range(period, ref)
    a, b = aware(start), aware(end)
    waiters = []
    for u in User.objects.filter(role__in=(Role.WAITER, Role.MANAGER, Role.OWNER)):
        orders = Order.objects.filter(waiter=u, opened_at__gte=a, opened_at__lt=b).exclude(status=Order.Status.VOID)
        paid = orders.filter(status=Order.Status.PAID)
        served = OrderItem.objects.filter(served_by=u, served_at__gte=a, served_at__lt=b)
        waits = [(i.served_at - i.ready_at).total_seconds() for i in served.only("served_at", "ready_at") if i.ready_at]
        row = {"u": u, "tables": orders.count(), "guests": orders.aggregate(g=Sum("guests"))["g"] or 0,
               "sales": paid.aggregate(t=Sum("total"))["t"] or 0, "tips": paid.aggregate(t=Sum("tip"))["t"] or 0,
               "served": served.count(), "pickup": round(sum(waits) / len(waits) / 60, 1) if waits else None}
        if row["tables"] or row["served"]:
            waiters.append(row)
    cooks = []
    for u in User.objects.filter(role__in=(Role.BARTENDER, Role.CHEF, Role.MANAGER, Role.OWNER)):
        done = OrderItem.objects.filter(prepared_by=u, ready_at__gte=a, ready_at__lt=b)
        secs = [i.prep_seconds for i in done.only("ready_at", "submitted_at") if i.prep_seconds is not None]
        late = sum(1 for i in done.only("ready_at", "submitted_at", "est_minutes") if i.ready_at and i.ready_at > i.due_at)
        if done.exists():
            cooks.append({"u": u, "items": done.count(), "avg": round(sum(secs) / len(secs) / 60, 1) if secs else None,
                          "late": late, "on_time": round((1 - late / len(secs)) * 100) if secs else None})
    waiters.sort(key=lambda r: r["sales"], reverse=True)
    cooks.sort(key=lambda r: r["items"], reverse=True)
    step = {"day": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=31)}[period]
    return render(request, "pos/performance.html", {
        "waiters": waiters, "cooks": cooks, "period": period, "ref": ref, "start": start, "end": end - timedelta(days=1),
        "prev": ref - step, "next": ref + step, "s": PosSettings.load(),
    })


# ------------------------------------------------------------------ settings

@require("pos_settings")
def pos_settings(request):
    form = PosSettingsForm(request.POST or None, instance=PosSettings.load())
    if request.method == "POST" and form.is_valid():
        form.save()
        services.bump()
        log_activity(request, "update", "POS settings changed", "settings")
        messages.success(request, _("Settings saved."))
        return redirect("pos:settings")
    return render(request, "pos/settings.html", {"form": form})


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@require("pos_settings")
def reservation_settings(request):
    obj = PosSettings.load()
    form = ReservationSettingsForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        s = form.save(commit=False)
        hours = {}
        for d in range(7):
            if request.POST.get(f"open_{d}"):
                hours[str(d)] = [request.POST.get(f"from_{d}") or "12:00", request.POST.get(f"to_{d}") or "22:00"]
            else:
                hours[str(d)] = []
        s.opening_hours = hours
        s.save()
        services.bump()
        log_activity(request, "update", "Reservation rules changed", "settings")
        messages.success(request, _("Settings saved."))
        return redirect("pos:reservation_settings")
    days = []
    for d, name in enumerate(WEEKDAYS):
        h = obj.hours.get(str(d)) or []
        days.append({"d": d, "name": name, "open": bool(h), "from": h[0] if h else "12:00", "to": h[1] if h else "22:00"})
    return render(request, "pos/reservation_settings.html", {"form": form, "days": days})
