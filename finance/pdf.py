"""Finance report PDF: restaurant logo in the header, contact details in the footer."""
import io

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.i18n import _
from pos.pdf import _logo


def report_pdf(f, brand, user=None):
    s = f["s"]
    buf = io.BytesIO()
    logo = _logo(brand)

    def header_footer(c, doc):
        w, h = A4
        c.saveState()
        x = doc.leftMargin
        if logo is not None:
            iw, ih = logo.getSize()
            lh = 14 * mm
            lw = min(iw * lh / ih, 50 * mm)
            c.drawImage(logo, x, h - 10 * mm - lh, lw, lh, mask="auto", preserveAspectRatio=True)
            x += lw + 5 * mm
        c.setFont("Helvetica-Bold", 13)
        c.drawString(x, h - 17 * mm, brand.name)
        c.setFont("Helvetica", 8.5)
        c.drawString(x, h - 22 * mm, " · ".join(p for p in (s.crib_number and f"CRIB {s.crib_number}", s.kvk_number and f"KvK {s.kvk_number}") if p))
        c.drawRightString(w - doc.rightMargin, h - 17 * mm, _("Financial report"))
        c.setStrokeColor(colors.HexColor("#c8c8c8"))
        c.line(doc.leftMargin, h - 27 * mm, w - doc.rightMargin, h - 27 * mm)
        # footer
        c.line(doc.leftMargin, 16 * mm, w - doc.rightMargin, 16 * mm)
        c.setFont("Helvetica", 8)
        c.drawString(doc.leftMargin, 11 * mm, brand.contact_line[:110])
        c.drawRightString(w - doc.rightMargin, 11 * mm, f"{_('Page')} {doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=34 * mm, bottomMargin=22 * mm,
                            title=f"{_('Financial report')} {f['start']:%d-%m-%Y}")
    st = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=st["Heading1"], fontSize=15, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=st["Heading2"], fontSize=11.5, spaceBefore=10, spaceAfter=4)
    small = ParagraphStyle("sm", parent=st["Normal"], fontSize=8, textColor=colors.HexColor("#555555"))
    period_names = {"day": _("Day"), "week": _("Week"), "month": _("Month"), "year": _("Year")}
    story = [
        Paragraph(f"{period_names[f['period']]}: {f['start']:%d-%m-%Y}" + (f" – {f['end']:%d-%m-%Y}" if f["end"] != f["start"] else ""), h1),
        Paragraph(_("Created {0} by {1}. Amounts in {2}.").format(timezone.localtime().strftime("%d-%m-%Y %H:%M"),
                  user.get_full_name() or user.username if user else "—", s.currency_code), small),
        Spacer(1, 6),
    ]

    def tbl(rows, widths, bold_last=False, header=True):
        t = Table(rows, colWidths=widths, hAlign="LEFT")
        style = [
            ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header:
            style += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f1f1"))]
        if bold_last:
            style += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9.5), ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black)]
        t.setStyle(TableStyle(style))
        return t

    m = s.fmt
    story += [Paragraph(_("Profit & Loss"), h2), tbl([
        [_("Item"), _("Amount")],
        [_("Gross sales (incl. {0})").format(s.tax_name), m(f["gross"])],
        [_("{0} collected").format(s.tax_name), m(-f["tax"])],
        [_("Net revenue"), m(f["net_revenue"])],
        [_("Expenses (excl. {0})").format(s.tax_name), m(-f["expenses_net"])],
        [_("Result before profit tax"), m(f["profit"])],
    ], [120 * mm, 50 * mm], bold_last=True)]

    story += [Paragraph(_("Sales"), h2), tbl([
        [_("Item"), _("Value")],
        [_("Paid bills"), str(f["payments"])], [_("Tables served"), str(f["orders"])], [_("Guests"), str(f["guests"])],
        [_("Average per table"), m(f["avg_ticket"])], [_("Average per guest"), m(f["per_guest"])],
        [_("Discounts given"), m(f["discounts"])], [_("Service charge"), m(f["service"])],
        [_("Cancelled orders"), str(f["voided"])],
    ], [120 * mm, 50 * mm])]

    rows = [[_("Payment method"), _("Bills"), _("Amount"), _("Tips")]]
    for row in f["methods"].values():
        rows.append([_(row["label"]), str(row["n"]), m(row["amount"]), m(row["tips"])])
    rows.append([_("Total"), str(f["payments"]), m(f["gross"]), m(f["tips"])])
    story += [Paragraph(_("Payments"), h2), tbl(rows, [70 * mm, 25 * mm, 40 * mm, 35 * mm], bold_last=True),
              Paragraph(_("Tips are paid to the staff and are not part of the revenue."), small)]

    story += [Paragraph(_("{0} (sales tax) summary").format(s.tax_name), h2), tbl([
        [_("Item"), _("Amount")],
        [_("{0} on sales ({1}%)").format(s.tax_name, s.tax_rate), m(f["tax"])],
        [_("{0} paid on expenses").format(s.tax_name), m(-f["expenses_tax"])],
        [_("Balance for the {0} return").format(s.tax_name), m(f["tax_payable"])],
    ], [120 * mm, 50 * mm], bold_last=True)]

    if f["by_cat"]:
        rows = [[_("Expense category"), _("Excl. {0}").format(s.tax_name), _("Incl. {0}").format(s.tax_name)]]
        for row in f["by_cat"].values():
            rows.append([_(row["label"]), m(row["net"]), m(row["amount"])])
        rows.append([_("Total"), m(f["expenses_net"]), m(f["expenses"])])
        story += [Paragraph(_("Expenses"), h2), tbl(rows, [90 * mm, 40 * mm, 40 * mm], bold_last=True)]

    if f["top"]:
        rows = [[_("Best sellers"), _("Qty"), _("Amount")]]
        for r in f["top"]:
            rows.append([r["name"][:60], str(r["n"]), m(r["amount"])])
        story += [Paragraph(_("Best sellers"), h2), tbl(rows, [110 * mm, 20 * mm, 40 * mm])]

    pays = list(f["payment_rows"])
    if pays and len(pays) <= 400:
        rows = [[_("Bill no."), _("Date"), _("Table"), _("Method"), _("Amount"), f"{s.tax_name}", _("Tip")]]
        for p in pays:
            rows.append([p.bill_number, timezone.localtime(p.paid_at).strftime("%d-%m %H:%M"), str(p.order.table_number),
                         _(p.get_method_display()), m(p.amount), m(p.tax_amount), m(p.tip)])
        story += [Paragraph(_("Bill register"), h2),
                  tbl(rows, [26 * mm, 26 * mm, 14 * mm, 20 * mm, 30 * mm, 25 * mm, 25 * mm])]
    story += [Spacer(1, 10), Paragraph(_("Keep this report with your administration. In Curaçao the bookkeeping must be kept for 10 years."), small)]
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return buf.getvalue()
