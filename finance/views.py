import csv
from datetime import date, timedelta

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.forms import StyledMixin
from core.i18n import _
from core.permissions import require
from core.utils import log_activity
from pos.models import PosSettings
from website.models import Brand

from . import reports
from .models import Expense
from .pdf import report_pdf


def _period(request, default="month"):
    period = request.GET.get("period", default)
    if period not in reports.PERIODS:
        period = default
    try:
        ref = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        ref = timezone.localdate()
    return period, ref


@require("finance")
def overview(request):
    period, ref = _period(request, "month")
    f = reports.figures(period, ref)
    f["prev"] = reports.step(period, ref, -1)
    f["next"] = reports.step(period, ref, 1)
    return render(request, "finance/overview.html", f)


@require("finance")
def report(request):
    period, ref = _period(request, "day")
    if request.GET.get("download"):
        f = reports.figures(period, ref)
        pdf = report_pdf(f, Brand.load(), request.user)
        log_activity(request, "download", f"Finance report {period} {f['start']} downloaded", "finance")
        name = f"report-{period}-{f['start']:%Y%m%d}.pdf"
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'{"attachment" if request.GET.get("download") == "1" else "inline"}; filename="{name}"'
        return resp
    return render(request, "finance/report.html", {"period": period, "ref": ref, "s": PosSettings.load()})


@require("finance")
def export_csv(request):
    """Bill register or expenses as CSV for the accountant (Excel opens it)."""
    period, ref = _period(request, "month")
    f = reports.figures(period, ref)
    what = request.GET.get("what", "sales")
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{what}-{period}-{f["start"]:%Y%m%d}.csv"'
    resp.write("﻿")
    w = csv.writer(resp, delimiter=";")
    s = f["s"]
    if what == "expenses":
        w.writerow(["date", "category", "description", "supplier", "invoice", "amount_incl_tax", f"{s.tax_name.lower()}_amount", "method"])
        for e in f["expense_rows"]:
            w.writerow([e.date.isoformat(), e.get_category_display(), e.description, e.supplier, e.invoice_number,
                        f"{e.amount:.2f}", f"{e.tax_amount:.2f}", e.get_method_display()])
    else:
        w.writerow(["bill_number", "paid_at", "order_code", "table", "guest", "method", "subtotal", "discount",
                    "service", "amount_incl_tax", f"{s.tax_name.lower()}_amount", "tip", "received_by"])
        for p in f["payment_rows"]:
            w.writerow([p.bill_number, timezone.localtime(p.paid_at).strftime("%Y-%m-%d %H:%M"), p.order.code,
                        p.order.table_number, p.guest_no if p.guest_no is not None else "", p.method,
                        f"{p.subtotal:.2f}", f"{p.discount:.2f}", f"{p.service_charge:.2f}", f"{p.amount:.2f}",
                        f"{p.tax_amount:.2f}", f"{p.tip:.2f}", p.received_by.username if p.received_by else ""])
    log_activity(request, "download", f"CSV export {what} {period} {f['start']}", "finance")
    return resp


class ExpenseForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["date", "category", "description", "supplier", "invoice_number", "amount", "tax_amount", "method", "receipt"]
        widgets = {"date": forms.DateInput()}

    def clean(self):
        d = super().clean()
        if d.get("amount") is not None and d.get("tax_amount") is not None and d["tax_amount"] > d["amount"]:
            self.add_error("tax_amount", _("The OB part cannot be more than the amount."))
        return d


@require("finance")
def expenses(request):
    period, ref = _period(request, "month")
    start, end = reports.period_bounds(period, ref)
    qs = Expense.objects.filter(date__gte=start, date__lt=end).select_related("created_by")
    cat = request.GET.get("category")
    if cat in Expense.Category.values:
        qs = qs.filter(category=cat)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(description__icontains=q) | Q(supplier__icontains=q) | Q(invoice_number__icontains=q))
    total = qs.aggregate(t=Sum("amount"), tax=Sum("tax_amount"))
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "finance/expenses.html", {
        "page": page, "total": total, "period": period, "ref": ref, "start": start, "end": end - timedelta(days=1),
        "prev": reports.step(period, ref, -1), "next": reports.step(period, ref, 1),
        "categories": Expense.Category.choices, "cat": cat, "q": q, "s": PosSettings.load(),
    })


@require("finance")
def expense_edit(request, pk=None):
    obj = get_object_or_404(Expense, pk=pk) if pk else Expense()
    s = PosSettings.load()
    form = ExpenseForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST":
        if request.POST.get("delete") and obj.pk:
            desc = obj.description
            obj.delete()
            log_activity(request, "delete", f"Expense '{desc}' deleted", "finance")
            messages.success(request, _("{0} was deleted.").format(desc))
            return redirect("finance:expenses")
        if form.is_valid():
            e = form.save(commit=False)
            if not pk:
                e.created_by = request.user
            e.save()
            log_activity(request, "update" if pk else "create", f"Expense '{e.description}' {e.amount} saved", "finance")
            messages.success(request, _("{0} was saved.").format(e.description))
            return redirect(f"/dashboard/finance/expenses/?period=month&date={e.date}")
    return render(request, "finance/expense_form.html", {"form": form, "obj": obj, "s": s})


@require("finance")
def receipt_file(request, pk):
    e = get_object_or_404(Expense, pk=pk)
    if not e.receipt:
        raise Http404
    return FileResponse(e.receipt.open("rb"), filename=e.receipt.name.rsplit("/", 1)[-1])
