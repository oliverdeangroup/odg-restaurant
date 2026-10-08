"""Cassa (checkout), bills, day close and the order history."""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.i18n import _
from core.permissions import can, history_days, require
from core.utils import log_activity

from . import services
from .models import BILL_FORMATS, Bill, DayClose, Order, OrderItem, Payment, PosSettings, money
from .pdf import bill_pdf


def _dec(v, default="0"):
    try:
        return Decimal(str(v or default).replace(",", "."))
    except InvalidOperation:
        return Decimal(default)


def _open_orders():
    from django.db.models import F

    return Order.objects.filter(status__in=Order.OPEN_STATUSES).select_related("waiter", "customer").annotate(
        amount=Sum(F("items__unit_price") * F("items__qty"), filter=~Q(items__status=OrderItem.Status.VOID) & Q(items__paid=False)),
    ).order_by("status", "table_number")  # "billing" sorts before "open"


@require("cassa")
def cassa(request, order_id=None):
    order = get_object_or_404(Order, pk=order_id) if order_id else None
    ctx = {"orders": _open_orders(), "order": order, "s": PosSettings.load(), "formats": BILL_FORMATS,
           "can_pay": can(request.user, "cassa_pay")}
    if request.GET.get("partial") == "list":
        return render(request, "pos/_cassa_list.html", ctx)
    bill_id = request.GET.get("paid") or request.session.pop("print_bill", None)
    ctx["paid_bill"] = Bill.objects.filter(pk=bill_id).select_related("order").first() if str(bill_id or "").isdigit() else None
    if order is not None:
        groups = services.bill_groups(order)
        unpaid = [i for its in groups.values() for i in its if not i.paid]
        ctx.update({
            "groups": [{"guest": g, "items": its, "unpaid": [i for i in its if not i.paid],
                        "totals": services.calc([i for i in its if not i.paid] or its)}
                       for g, its in groups.items()],
            "unpaid_totals": services.calc(unpaid),
            "unpaid_subtotal": services.calc(unpaid)["subtotal"],
            "has_unpaid": bool(unpaid),
            "payments": order.payments.select_related("received_by"),
            "bills": order.bills.all(),
            "waiting": sum(1 for i in unpaid if i.status in (OrderItem.Status.QUEUED, OrderItem.Status.PREPARING)),
        })
        if request.GET.get("partial") == "detail":
            return render(request, "pos/_cassa_detail.html", ctx)
    return render(request, "pos/cassa.html", ctx)


def payment_totals(p):
    """The amounts of a saved payment, in the shape of services.calc()."""
    return {"subtotal": p.subtotal, "discount": p.discount, "service": p.service_charge, "tax": p.tax_amount,
            "rate": p.order.tax_rate or PosSettings.load().tax_rate, "total": p.amount, "net": p.amount - p.tax_amount}


def _save_bill(order, items, totals, fmt, user, payment=None, guest_no=None, tip=Decimal("0")):
    number = payment.bill_number if payment else ""
    pdf = bill_pdf(order, items, totals, fmt, payment=payment, guest_no=guest_no, number=number, tip=tip)
    bill = Bill(order=order, payment=payment, guest_no=guest_no, number=number, is_receipt=payment is not None,
                fmt=fmt, total=totals["total"] + tip, created_by=user)
    kind = "receipt" if payment else "proforma"
    suffix = f"-g{guest_no}" if guest_no is not None else ""
    bill.file.save(f"{order.code}-{kind}{suffix}-{timezone.now():%H%M%S}.pdf", ContentFile(pdf), save=True)
    return bill


def _guest(request):
    g = request.POST.get("guest", "all")
    return None if g in ("", "all") else int(g) if g.isdigit() else None


@require("cassa_pay")
@require_POST
def proforma(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    guest = _guest(request)
    qs = order.live_items().filter(paid=False)
    if guest is not None:
        qs = qs.filter(guest_no=guest)
    items = list(qs)
    if not items:
        messages.error(request, _("Nothing left to pay."))
        return redirect("pos:cassa_order", order.pk)
    fmt = request.POST.get("fmt") or PosSettings.load().default_bill_format
    totals = services.calc(items, _dec(request.POST.get("discount")))
    bill = _save_bill(order, items, totals, fmt, request.user, guest_no=guest)
    if order.status == Order.Status.OPEN:
        order.status = Order.Status.BILLING
        order.save(update_fields=["status"])
        services.bump()
    return redirect("pos:bill", bill.pk)


@require("cassa_pay")
@require_POST
def pay(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    if not order.is_open:
        messages.error(request, _("This order is already closed."))
        return redirect("pos:cassa")
    guest = _guest(request)
    method = request.POST.get("method")
    if method not in Payment.Method.values:
        messages.error(request, _("Choose cash or card."))
        return redirect("pos:cassa_order", order.pk)
    discount = _dec(request.POST.get("discount"))
    tip = _dec(request.POST.get("tip"))
    received = _dec(request.POST.get("received"))
    fmt = request.POST.get("fmt") or PosSettings.load().default_bill_format
    qs = order.live_items().filter(paid=False)
    if guest is not None:
        qs = qs.filter(guest_no=guest)
    items = list(qs)
    try:
        payment = services.pay(order, request.user, method, guest, tip=tip, received=received, discount=discount)
    except ValueError as e:
        messages.error(request, _(str(e)))
        return redirect("pos:cassa_order", order.pk)
    totals = payment_totals(payment)
    bill = _save_bill(order, items, totals, fmt, request.user, payment=payment, guest_no=guest, tip=payment.tip)
    log_activity(request, "create", f"Bill {payment.bill_number} paid ({payment.method}) for order {order.code}", "cassa")
    order.refresh_from_db()
    if order.status == Order.Status.PAID:
        messages.success(request, _("Table {0} is paid and free again. Bill {1}.").format(order.table_number, payment.bill_number))
    else:
        messages.success(request, _("Payment saved. Bill {0}.").format(payment.bill_number))
    request.session["print_bill"] = bill.pk
    return redirect("pos:cassa_order", order.pk) if order.is_open else redirect(f"/dashboard/pos/cassa/?paid={bill.pk}")


@require("cassa_pay")
@require_POST
def void_order(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, _("Give a reason for cancelling."))
        return redirect("pos:cassa_order", order.pk)
    try:
        services.void_order(order, request.user, reason)
    except ValueError as e:
        messages.error(request, _(str(e)))
        return redirect("pos:cassa_order", order.pk)
    log_activity(request, "delete", f"Order {order.code} cancelled: {reason}", "cassa")
    messages.success(request, _("Order {0} was cancelled.").format(order.code))
    return redirect("pos:cassa")


@require("cassa", "history")
def bill_file(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    if not can(request.user, "cassa") and not _in_history_window(request.user, bill.order):
        raise Http404
    resp = FileResponse(bill.file.open("rb"), content_type="application/pdf",
                        as_attachment=request.GET.get("download") == "1",
                        filename=bill.file.name.rsplit("/", 1)[-1])
    return resp


# ------------------------------------------------------------------ day close

def day_figures(day):
    pays = Payment.objects.filter(paid_at__date=day)
    cash = pays.filter(method=Payment.Method.CASH).aggregate(a=Sum("amount"), t=Sum("tip"))
    card = pays.filter(method=Payment.Method.CARD).aggregate(a=Sum("amount"), t=Sum("tip"))
    return {
        "cash": money((cash["a"] or 0) + (cash["t"] or 0)),
        "card": money((card["a"] or 0) + (card["t"] or 0)),
        "sales": money(pays.aggregate(a=Sum("amount"))["a"] or 0),
        "tips": money(pays.aggregate(t=Sum("tip"))["t"] or 0),
        "count": pays.count(),
        "open_orders": Order.objects.filter(status__in=Order.OPEN_STATUSES).count(),
    }


@require("cassa_pay")
def day_close(request):
    try:
        day = date.fromisoformat(request.GET.get("date") or request.POST.get("date") or "")
    except ValueError:
        day = timezone.localdate()
    existing = DayClose.objects.filter(date=day).first()
    fig = day_figures(day)
    if request.method == "POST" and existing is None:
        opening = _dec(request.POST.get("opening_cash"))
        dc = DayClose.objects.create(
            date=day, opening_cash=opening, expected_cash=opening + fig["cash"], counted_cash=_dec(request.POST.get("counted_cash")),
            card_total=fig["card"], sales_total=fig["sales"], tips_total=fig["tips"],
            note=request.POST.get("note", "")[:255], closed_by=request.user,
        )
        log_activity(request, "create", f"Day {day} closed (difference {dc.difference})", "cassa")
        messages.success(request, _("The day is closed."))
        return redirect(f"{request.path}?date={day}")
    return render(request, "pos/day_close.html", {"day": day, "fig": fig, "existing": existing, "s": PosSettings.load()})


@require("finance")
def day_closes(request):
    page = Paginator(DayClose.objects.select_related("closed_by"), 40).get_page(request.GET.get("page"))
    return render(request, "pos/day_closes.html", {"page": page, "s": PosSettings.load()})


# ------------------------------------------------------------------ history

def _in_history_window(user, order):
    return order.opened_at >= timezone.now() - timedelta(days=history_days(user))


def period_range(period, ref):
    """(start, end, label) for day / week / month around a date."""
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


def aware(d):
    return timezone.make_aware(datetime.combine(d, datetime.min.time()))


@require("history")
def history(request):
    days = history_days(request.user)
    limit = timezone.localdate() - timedelta(days=days - 1)
    period = request.GET.get("period", "day")
    if period not in ("day", "week", "month"):
        period = "day"
    try:
        ref = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        ref = timezone.localdate()
    start, end = period_range(period, ref)
    start = max(start, limit)
    qs = Order.objects.filter(opened_at__gte=aware(start), opened_at__lt=aware(end)).select_related("waiter", "customer")
    q = request.GET.get("q", "").strip()
    if q:
        cond = Q(code__icontains=q) | Q(bill_number__icontains=q) | Q(customer__last_name__icontains=q)
        if q.isdigit() and len(q) < 5:
            cond |= Q(table_number=int(q))
        qs = qs.filter(cond)
    status = request.GET.get("status")
    if status in Order.Status.values:
        qs = qs.filter(status=status)
    totals = qs.filter(status=Order.Status.PAID).aggregate(t=Sum("total"), tip=Sum("tip"))
    page = Paginator(qs.order_by("-opened_at"), 50).get_page(request.GET.get("page"))
    step = {"day": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=31)}[period]
    return render(request, "pos/history.html", {
        "page": page, "period": period, "ref": ref, "start": start, "end": end - timedelta(days=1), "q": q,
        "status": status, "totals": totals, "days": days, "limit": limit,
        "prev": max(ref - step, limit) if ref > limit else None,
        "next": min(ref + step, timezone.localdate()) if ref < timezone.localdate() else None,
        "statuses": Order.Status.choices, "s": PosSettings.load(),
    })


@require("history", "cassa")
def history_order(request, pk):
    order = get_object_or_404(Order.objects.select_related("waiter", "customer", "reservation", "paid_by"), pk=pk)
    if not can(request.user, "cassa") and not _in_history_window(request.user, order):
        raise Http404
    return render(request, "pos/history_order.html", {
        "order": order, "items": order.items.select_related("prepared_by", "served_by", "added_by").order_by("batch", "guest_no", "id"),
        "payments": order.payments.select_related("received_by"), "bills": order.bills.all(), "s": PosSettings.load(),
    })
