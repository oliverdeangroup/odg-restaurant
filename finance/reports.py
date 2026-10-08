"""Profit & Loss figures for a period, shared by the screen, the PDF and the CSV export.

Revenue is counted on the day a bill is paid (cash basis). Amounts:
* Gross sales  = what guests paid, including OB, without tips
* OB collected = the sales tax inside those amounts (to be paid to the Tax Office)
* Net revenue  = gross sales − OB
* Tips are shown separately: they belong to the staff, not to the revenue.
* Expenses are entered including OB; the OB part can be deducted in the OB return.
"""
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.utils import timezone

from pos.models import Order, OrderItem, Payment, PosSettings, money

from .models import Expense

PERIODS = ("day", "week", "month", "year")


def period_bounds(period, ref):
    if period == "week":
        start = ref - timedelta(days=ref.weekday())
        end = start + timedelta(days=7)
    elif period == "month":
        start = ref.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
    elif period == "year":
        start = ref.replace(month=1, day=1)
        end = start.replace(year=start.year + 1)
    else:
        start, end = ref, ref + timedelta(days=1)
    return start, end


def step(period, ref, direction):
    start, end = period_bounds(period, ref)
    if direction > 0:
        return end
    if period == "day":
        return ref - timedelta(days=1)
    return period_bounds(period, start - timedelta(days=1))[0]


def _aware(d):
    return timezone.make_aware(datetime.combine(d, datetime.min.time()))


def figures(period, ref):
    s = PosSettings.load()
    start, end = period_bounds(period, ref)
    a, b = _aware(start), _aware(end)
    pays = Payment.objects.filter(paid_at__gte=a, paid_at__lt=b)
    agg = pays.aggregate(gross=Sum("amount"), tax=Sum("tax_amount"), tips=Sum("tip"), disc=Sum("discount"),
                         service=Sum("service_charge"), sub=Sum("subtotal"), n=Count("id"))
    gross = money(agg["gross"] or 0)
    tax = money(agg["tax"] or 0)
    methods = OrderedDict()
    for m, label in Payment.Method.choices:
        r = pays.filter(method=m).aggregate(t=Sum("amount"), tip=Sum("tip"), n=Count("id"))
        methods[m] = {"label": label, "amount": money(r["t"] or 0), "tips": money(r["tip"] or 0), "n": r["n"]}
    orders = Order.objects.filter(status=Order.Status.PAID, closed_at__gte=a, closed_at__lt=b)
    n_orders = orders.count()
    guests = orders.aggregate(g=Sum("guests"))["g"] or 0
    voided = Order.objects.filter(status=Order.Status.VOID, closed_at__gte=a, closed_at__lt=b).count()

    expenses = Expense.objects.filter(date__gte=start, date__lt=end)
    exp_total = money(expenses.aggregate(t=Sum("amount"))["t"] or 0)
    exp_tax = money(expenses.aggregate(t=Sum("tax_amount"))["t"] or 0)
    by_cat = OrderedDict()
    for code, label in Expense.Category.choices:
        r = expenses.filter(category=code).aggregate(t=Sum("amount"), tax=Sum("tax_amount"))
        if r["t"]:
            by_cat[code] = {"label": label, "amount": money(r["t"]), "net": money(r["t"] - (r["tax"] or 0))}

    net_revenue = gross - tax
    exp_net = exp_total - exp_tax
    profit = net_revenue - exp_net

    # Sales per station / category / product
    items = OrderItem.objects.filter(order__in=orders).exclude(status=OrderItem.Status.VOID)
    top = list(items.values("name").annotate(n=Sum("qty"), amount=Sum(F("unit_price") * F("qty"))).order_by("-amount")[:10])
    stations = {r["station"]: money(r["amount"] or 0) for r in items.values("station").annotate(amount=Sum(F("unit_price") * F("qty")))}

    # Bars per day (or per month for a year)
    buckets = OrderedDict()
    if period == "year":
        for m in range(1, 13):
            buckets[date(start.year, m, 1)] = Decimal("0")
    else:
        d = start
        while d < end:
            buckets[d] = Decimal("0")
            d += timedelta(days=1)
    for p in pays.values("paid_at", "amount"):
        local = timezone.localtime(p["paid_at"]).date()
        key = local.replace(day=1) if period == "year" else local
        if key in buckets:
            buckets[key] += p["amount"]
    peak = max(buckets.values(), default=0) or 1
    chart = [{"d": k, "v": money(v), "pct": round(v / peak * 100)} for k, v in buckets.items()]

    return {
        "s": s, "period": period, "ref": ref, "start": start, "end": end - timedelta(days=1),
        "gross": gross, "tax": tax, "net_revenue": net_revenue, "tips": money(agg["tips"] or 0),
        "discounts": money(agg["disc"] or 0), "service": money(agg["service"] or 0), "subtotal": money(agg["sub"] or 0),
        "payments": agg["n"] or 0, "orders": n_orders, "guests": guests, "voided": voided,
        "avg_ticket": money(gross / n_orders) if n_orders else Decimal("0.00"),
        "per_guest": money(gross / guests) if guests else Decimal("0.00"),
        "methods": methods, "expenses": exp_total, "expenses_tax": exp_tax, "expenses_net": exp_net,
        "by_cat": by_cat, "profit": profit, "tax_payable": tax - exp_tax, "top": top, "stations": stations,
        "chart": chart, "expense_rows": expenses.order_by("date", "id"),
        "payment_rows": pays.select_related("order", "received_by").order_by("paid_at"),
    }
