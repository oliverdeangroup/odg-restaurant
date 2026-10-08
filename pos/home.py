"""HOME tab: a personalized overview for every role."""
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from core.i18n import _
from core.models import ActivityLog, DemoSandbox, Role, SystemUpdate, User
from core.permissions import perms_for

from .models import Customer, Order, OrderItem, Payment, PosSettings, Reservation, Station


def quick_actions(perms):
    acts = []
    for perm, label, icon, url in (
        ("pos_waiter", "Take orders", "pos", "pos:tables"),
        ("pos_bar", "Bar queue", "glass", "pos:bar"),
        ("pos_kitchen", "Kitchen queue", "chef", "pos:kitchen"),
        ("pos_overview", "Live overview", "eye", "pos:overview"),
        ("cassa", "Cassa", "cash", "pos:cassa"),
        ("floor", "Floor", "grid", "pos:floor"),
        ("reservations", "New reservation", "calendar", "pos:reservation_new"),
        ("customers", "Customers", "users", "pos:customers"),
        ("finance", "Finance", "chart", "finance:overview"),
        ("products", "Products", "list", "pos:products"),
        ("website", "Website", "globe", "website:pages"),
        ("users_staff", "Add a user", "user", "core:users_staff"),
    ):
        if perm in perms:
            acts.append({"label": label, "icon": icon, "url": reverse(url)})
    return acts[:8]


def home_context(request):
    user = request.user
    perms = perms_for(user)
    s = PosSettings.load()
    now = timezone.now()
    today = timezone.localdate()
    open_orders = Order.objects.filter(status__in=Order.OPEN_STATUSES)
    ctx = {"actions": quick_actions(perms), "s": s,
           "notes": user.notifications.all()[:8], "role": user.role}
    cards = []

    if "pos_waiter" in perms:
        mine = open_orders.filter(waiter=user) if user.role == Role.WAITER else open_orders
        ready = OrderItem.objects.filter(order__in=mine, status=OrderItem.Status.READY).select_related("order").order_by("ready_at")
        ctx["pickup"] = ready[:12]
        ctx["my_tables"] = mine.select_related("table").annotate(
            n_ready=Count("items", filter=Q(items__status=OrderItem.Status.READY)),
            n_wait=Count("items", filter=Q(items__status__in=(OrderItem.Status.QUEUED, OrderItem.Status.PREPARING))),
        ).order_by("table_number")
        if user.role == Role.WAITER:
            cards += [
                {"label": _("My open tables"), "value": mine.count(), "icon": "grid"},
                {"label": _("Ready to pick up"), "value": ready.count(), "icon": "bell", "hot": ready.exists()},
                {"label": _("Served today"), "value": OrderItem.objects.filter(served_by=user, served_at__date=today).count(), "icon": "check"},
            ]
    for station, perm, label in ((Station.BAR, "pos_bar", _("Bar")), (Station.KITCHEN, "pos_kitchen", _("Kitchen"))):
        if perm in perms and user.role in (Role.BARTENDER, Role.CHEF):
            q = OrderItem.objects.filter(station=station, status__in=(OrderItem.Status.QUEUED, OrderItem.Status.PREPARING),
                                         order__status__in=Order.OPEN_STATUSES)
            oldest = q.order_by("submitted_at").first()
            done = OrderItem.objects.filter(station=station, ready_at__date=today)
            secs = [i.prep_seconds for i in done.only("ready_at", "submitted_at") if i.prep_seconds is not None]
            cards += [
                {"label": _("Waiting in the {0} queue").format(label.lower()), "value": q.count(), "icon": "clock", "hot": q.exists()},
                {"label": _("Completed today"), "value": done.count(), "icon": "check"},
                {"label": _("Average preparation"), "value": f"{round(sum(secs) / len(secs) / 60, 1)} min" if secs else "—", "icon": "clock"},
                {"label": _("Oldest ticket"), "value": f"{int((now - oldest.submitted_at).total_seconds() // 60)} min" if oldest else "—", "icon": "alert"},
            ]
            ctx["station_url"] = reverse("pos:bar" if station == Station.BAR else "pos:kitchen")

    if "pos_overview" in perms:
        paid_today = Payment.objects.filter(paid_at__date=today)
        res_today = Reservation.objects.filter(start__date=today, status__in=Reservation.ACTIVE + (Reservation.Status.COMPLETED,))
        cards += [
            {"label": _("Open tables"), "value": open_orders.count(), "icon": "grid"},
            {"label": _("Guests seated"), "value": open_orders.aggregate(g=Sum("guests"))["g"] or 0, "icon": "users"},
            {"label": _("Items waiting"), "value": OrderItem.objects.filter(order__in=open_orders, status__in=(OrderItem.Status.QUEUED, OrderItem.Status.PREPARING)).count(), "icon": "clock"},
            {"label": _("Reservations today"), "value": res_today.count(), "icon": "calendar"},
        ]
        if "finance" in perms or "cassa_pay" in perms:
            cards.append({"label": _("Sales today"), "value": s.fmt(paid_today.aggregate(t=Sum("amount"))["t"] or 0), "icon": "cash"})
            cards.append({"label": _("Tips today"), "value": s.fmt(paid_today.aggregate(t=Sum("tip"))["t"] or 0), "icon": "star"})
        ctx["upcoming"] = Reservation.objects.filter(
            start__gte=now - timedelta(minutes=s.no_show_minutes), start__lte=now + timedelta(hours=6),
            status__in=(Reservation.Status.CONFIRMED, Reservation.Status.PENDING)).select_related("customer", "table")[:8]
        ctx["billing"] = open_orders.filter(status=Order.Status.BILLING).order_by("table_number")

    if "finance" in perms:
        week_start = today - timedelta(days=6)
        per_day = {}
        for p in Payment.objects.filter(paid_at__date__gte=week_start).values("paid_at", "amount"):
            d = timezone.localtime(p["paid_at"]).date()
            per_day[d] = per_day.get(d, 0) + p["amount"]
        peak = max(per_day.values(), default=0) or 1
        ctx["week"] = [{"d": week_start + timedelta(days=i), "v": per_day.get(week_start + timedelta(days=i), 0),
                        "pct": round(per_day.get(week_start + timedelta(days=i), 0) / peak * 100)} for i in range(7)]

    if user.is_system:
        ctx["system"] = {
            "users": User.objects.filter(is_active=True).count(),
            "customers": Customer.objects.count(),
            "updates": SystemUpdate.objects.all()[:3],
            "failed_logins": ActivityLog.objects.filter(area="login_failed", created_at__gte=now - timedelta(days=7)).count(),
            "demo_week": DemoSandbox.objects.filter(created_at__gte=now - timedelta(days=7)).count(),
            "activity": ActivityLog.objects.select_related("user").exclude(area="login_failed")[:8],
        }
    ctx["cards"] = cards
    return ctx
