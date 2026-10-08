"""PDF bills in three sizes: 80 mm receipt, A5 and A4."""
import io
from decimal import Decimal

from django.utils import timezone
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from core.i18n import _

from .models import PosSettings, money


def _logo(brand):
    if not brand.logo:
        return None
    name = brand.logo.name.lower()
    if not name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return None
    try:
        with brand.logo.open("rb") as fh:
            return ImageReader(io.BytesIO(fh.read()))
    except Exception:  # noqa: BLE001 - a missing logo never blocks a bill
        return None


def bill_pdf(order, items, totals, fmt="80mm", payment=None, guest_no=None, number="", tip=Decimal("0")):
    """Returns PDF bytes. Without a payment the bill is marked PRO FORMA."""
    from website.models import Brand

    s = PosSettings.load()
    brand = Brand.load()
    receipt = fmt == "80mm"
    # Lines needed → height for the receipt roll
    n_lines = sum(1 + len(i.options) + (1 if i.notes else 0) for i in items)
    if receipt:
        width = 80 * mm
        height = max(115 * mm, (88 + n_lines * 4.6) * mm + (16 * mm if brand.logo else 0))
        margin, fs = 4 * mm, 8.2
    else:
        width, height = A5 if fmt == "a5" else A4
        margin, fs = (12 if fmt == "a5" else 18) * mm, 9 if fmt == "a5" else 10
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setTitle(f"{_('Bill')} {number or order.code}")
    y = height - margin
    right = width - margin
    center = width / 2

    def line(text, x=None, size=fs, bold=False, align="left", gap=1.35):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        if align == "center":
            c.drawCentredString(center, y - size, text)
        elif align == "right":
            c.drawRightString(x or right, y - size, text)
        else:
            c.drawString(x or margin, y - size, text)
        return size * gap

    def advance(h):
        nonlocal y
        y -= h

    def rule():
        nonlocal y
        y -= 2
        c.setLineWidth(0.5)
        c.setDash(1, 2) if receipt else c.setDash()
        c.line(margin, y, right, y)
        c.setDash()
        y -= 4

    # ---------------- header
    logo = _logo(brand)
    if logo is not None:
        iw, ih = logo.getSize()
        h = (16 if receipt else 20) * mm
        w = min(iw * h / ih, width - 2 * margin)
        c.drawImage(logo, center - w / 2, y - h, w, h, mask="auto", preserveAspectRatio=True)
        advance(h + 4)
    advance(line(brand.name, size=fs + 4, bold=True, align="center"))
    for t in (brand.address and f"{brand.address}, {brand.city}" or brand.city, brand.phone, brand.email):
        if t:
            advance(line(t, size=fs - 0.5, align="center"))
    ids = " · ".join(x for x in (s.crib_number and f"CRIB {s.crib_number}", s.kvk_number and f"KvK {s.kvk_number}") if x)
    if ids:
        advance(line(ids, size=fs - 1, align="center"))
    if s.bill_header_text:
        advance(line(s.bill_header_text, size=fs - 0.5, align="center"))
    advance(4)
    title = _("RECEIPT") if payment else _("PRO FORMA — NOT A RECEIPT")
    advance(line(title, size=fs + 1.5, bold=True, align="center"))
    rule()
    when = timezone.localtime(payment.paid_at if payment else timezone.now())
    meta = [
        (_("Bill no."), number or "—"),
        (_("Date"), when.strftime("%d-%m-%Y %H:%M")),
        (_("Table"), str(order.table_number)),
        (_("Order code"), order.code),
    ]
    if guest_no is not None:
        meta.append((_("Guest"), _("Table (shared)") if guest_no == 0 else f"#{guest_no}"))
    if order.waiter:
        meta.append((_("Served by"), order.waiter.first_name or order.waiter.username))
    for k, v in meta:
        line(k, size=fs - 0.5)
        advance(line(v, size=fs - 0.5, align="right"))
    rule()

    # ---------------- items
    col_qty = margin
    col_name = margin + (7 if receipt else 12) * mm
    for it in items:
        if y < margin + 40 * mm and not receipt:
            c.showPage()
            y = height - margin
        name = it.name
        maxlen = 26 if receipt else 60
        line(f"{it.qty}×", col_qty)
        line(name[:maxlen], col_name)
        advance(line(f"{money(it.unit_price * it.qty):,.2f}", align="right"))
        for o in it.options:
            advance(line(o[:maxlen + 6], col_name, size=fs - 1.5))
        if it.notes:
            advance(line(f"“{it.notes[:maxlen + 4]}”", col_name, size=fs - 1.5))
    rule()

    # ---------------- totals
    def money_row(label, amount, bold=False, size=fs):
        line(label, size=size, bold=bold)
        advance(line(s.fmt(amount), size=size, bold=bold, align="right"))

    money_row(_("Subtotal"), totals["subtotal"])
    if totals["discount"]:
        money_row(_("Discount"), -totals["discount"])
    if totals["service"]:
        money_row(_("Service charge"), totals["service"])
    if not s.prices_include_tax:
        money_row(f"{s.tax_name} {totals['rate']}%", totals["tax"])
    money_row(_("Total"), totals["total"], bold=True, size=fs + 2)
    if s.prices_include_tax:
        advance(line(_("Including {0} {1}%: {2}").format(s.tax_name, totals["rate"], s.fmt(totals["tax"])), size=fs - 1))
    if tip:
        money_row(_("Tip"), tip)
        money_row(_("Total paid"), totals["total"] + tip, bold=True)
    if payment:
        rule()
        money_row(_("Paid by {0}").format(_(payment.get_method_display()).lower()), payment.received)
        if payment.change:
            money_row(_("Change"), payment.change)
    else:
        advance(4)
        tips = s.tips
        if tips:
            advance(line(_("Tip suggestion") + ": " + " · ".join(f"{p}% = {s.fmt(totals['total'] * p / 100)}" for p in tips), size=fs - 1.5))
    rule()
    if s.bill_footer_text:
        advance(line(s.bill_footer_text, size=fs - 0.5, align="center"))
    if not receipt:
        # Contact details at the bottom of A4/A5 pages
        c.setFont("Helvetica", fs - 2)
        c.drawCentredString(center, margin / 2 + 4, brand.contact_line[:120])
    c.showPage()
    c.save()
    return buf.getvalue()
