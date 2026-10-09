import json
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.i18n import _
from core.models import ActivityLog, SystemSettings
from core.permissions import require
from core.utils import client_ip, log_activity

from . import builder
from .forms import AppearanceForm, BrandForm, MediaForm, MenuForm, MenuItemForm, PageForm, SEOForm
from .models import THEME_DEFAULTS, THEME_DESCRIPTIONS, THEMES, Appearance, Brand, MediaFile, Menu, MenuItem, Page, PageRevision, SEOSettings
from .sanitize import clean_html


# ================================================================ dashboard

@require("website")
def pages(request):
    qs = Page.objects.select_related("author", "parent")
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(content__icontains=q))
    counts = {"all": Page.objects.count(), "published": Page.objects.filter(status="published").count(),
              "draft": Page.objects.filter(status="draft").count()}
    page = Paginator(qs.order_by("-is_homepage", "order", "title"), 30).get_page(request.GET.get("page"))
    return render(request, "website/pages.html", {"page": page, "counts": counts, "status": status, "q": q})


def _builder_ctx():
    from core.i18n import translate
    from pos.models import Category

    return {
        "builder_spec": {
            "widgets": {t: {"label": translate(builder.WIDGET_LABELS[t]), "icon": builder.WIDGET_ICONS[t], "fields": spec}
                        for t, spec in builder.WIDGETS.items()},
            "fields": {k: translate(v) for k, v in builder.FIELD_LABELS.items()},
            "choices": {k: translate(v) for k, v in builder.CHOICE_LABELS.items()},
            "layouts": list(builder.LAYOUTS.items()),
            "icons": builder.ICONS,
            "categories": [{"id": c.pk, "name": c.path} for c in Category.objects.filter(active=True)],
            "media": reverse("website:media"),
        },
        "look": Appearance.load(),
    }


@require("website")
def page_edit(request, pk=None):
    obj = get_object_or_404(Page, pk=pk) if pk else Page(author=request.user, editor=request.GET.get("editor") or Page.Editor.BUILDER)
    form = PageForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST":
        try:
            layout = builder.clean_layout(json.loads(request.POST.get("layout") or "{}"))
        except ValueError:
            layout = {"sections": []}
        if form.is_valid():
            is_new = obj.pk is None
            if not is_new:
                old = Page.objects.get(pk=obj.pk)
                if old.content != form.cleaned_data["content"] or old.title != form.cleaned_data["title"] or old.layout != layout:
                    PageRevision.objects.create(page=old, title=old.title, content=old.content, layout=old.layout, created_by=request.user)
            page = form.save(commit=False)
            page.layout = layout
            if request.POST.get("publish"):
                page.status = Page.Status.PUBLISHED
            page.save()
            log_activity(request, "create" if is_new else "update", f"Page '{page.title}' saved", "website")
            if request.headers.get("x-requested-with") == "fetch":
                return JsonResponse({"ok": True, "id": page.pk, "url": page.get_absolute_url(), "status": page.status,
                                     "edit": reverse("website:page_edit", args=[page.pk])})
            messages.success(request, _("Page saved."))
            return redirect("website:page_edit", page.pk)
        if request.headers.get("x-requested-with") == "fetch":
            return JsonResponse({"ok": False, "errors": {k: [str(e) for e in v] for k, v in form.errors.items()}}, status=400)
    ctx = _builder_ctx()
    ctx.update({"form": form, "obj": obj, "layout": obj.layout or {"sections": []},
                "revisions": obj.revisions.select_related("created_by")[:15] if obj.pk else []})
    return render(request, "website/page_edit.html", ctx)


@require("website")
@require_POST
def page_delete(request, pk):
    obj = get_object_or_404(Page, pk=pk)
    title = obj.title
    obj.delete()
    log_activity(request, "delete", f"Page '{title}' deleted", "website")
    messages.success(request, _("{0} was deleted.").format(title))
    return redirect("website:pages")


@require("website")
@require_POST
def page_duplicate(request, pk):
    obj = get_object_or_404(Page, pk=pk)
    obj.pk = None
    obj.title = f"{obj.title} (copy)"
    obj.slug = f"{obj.slug}-copy"
    n = 2
    while Page.objects.filter(slug=obj.slug).exists():
        obj.slug = f"{obj.slug.rsplit('-copy', 1)[0]}-copy-{n}"
        n += 1
    obj.status, obj.is_homepage, obj.published_at = Page.Status.DRAFT, False, None
    obj.save()
    return redirect("website:page_edit", obj.pk)


@require("website")
@require_POST
def revision_restore(request, pk):
    rev = get_object_or_404(PageRevision, pk=pk)
    page = rev.page
    PageRevision.objects.create(page=page, title=page.title, content=page.content, layout=page.layout, created_by=request.user)
    page.title, page.content, page.layout = rev.title, rev.content, rev.layout or page.layout
    page.save()
    messages.success(request, _("The older version was restored."))
    return redirect("website:page_edit", page.pk)


@require("website")
def appearance(request):
    obj = Appearance.load()
    form = AppearanceForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST":
        action = request.POST.get("action", "appearance")
        if action == "appearance" and form.is_valid():
            form.save()
            log_activity(request, "update", "Website appearance changed", "website")
            messages.success(request, _("Appearance saved."))
            return redirect("website:appearance")
        if action == "theme":
            theme = request.POST.get("theme")
            if theme in dict(THEMES):
                obj.theme = theme
                if request.POST.get("colors"):
                    for k, v in THEME_DEFAULTS[theme].items():
                        setattr(obj, k, v)
                obj.save()
                log_activity(request, "update", f"Theme {theme} activated", "website")
                messages.success(request, _("Theme activated. Your pages and data are not changed."))
            return redirect("website:appearance")
    return render(request, "website/appearance.html", {
        "form": form, "obj": obj, "themes": [(k, n, THEME_DESCRIPTIONS[k], THEME_DEFAULTS[k]) for k, n in THEMES],
    })


@require("website")
def footer_builder(request):
    obj = Appearance.load()
    if request.method == "POST":
        try:
            obj.footer_layout = builder.clean_layout(json.loads(request.POST.get("layout") or "{}"))
        except ValueError:
            return HttpResponseBadRequest("Bad layout")
        obj.save(update_fields=["footer_layout"])
        log_activity(request, "update", "Website footer changed", "website")
        if request.headers.get("x-requested-with") == "fetch":
            return JsonResponse({"ok": True})
        messages.success(request, _("Footer saved."))
        return redirect("website:footer")
    ctx = _builder_ctx()
    ctx.update({"layout": obj.footer_layout or {"sections": []}, "is_footer": True})
    return render(request, "website/footer_edit.html", ctx)


@require("website")
def menus(request, pk=None):
    all_menus = Menu.objects.all()
    menu = get_object_or_404(Menu, pk=pk) if pk else all_menus.first()
    mform = MenuForm(prefix="m")
    iform = MenuItemForm(prefix="i", menu=menu)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "menu":
            inst = get_object_or_404(Menu, pk=request.POST["pk"]) if request.POST.get("pk") else None
            mform = MenuForm(request.POST, instance=inst, prefix="m")
            if mform.is_valid():
                m = mform.save()
                if m.location != Menu.Location.NONE:
                    Menu.objects.filter(location=m.location).exclude(pk=m.pk).update(location=Menu.Location.NONE)
                messages.success(request, _("Menu saved."))
                return redirect("website:menu", m.pk)
        elif action == "menu_delete" and menu:
            menu.delete()
            return redirect("website:menus")
        elif action == "item" and menu:
            inst = get_object_or_404(MenuItem, pk=request.POST["pk"], menu=menu) if request.POST.get("pk") else None
            iform = MenuItemForm(request.POST, instance=inst, prefix="i", menu=menu)
            if iform.is_valid():
                item = iform.save(commit=False)
                item.menu = menu
                item.label = iform.cleaned_data["label"]
                if item.parent_id == item.pk:
                    item.parent = None
                item.save()
                messages.success(request, _("Menu item saved."))
                return redirect("website:menu", menu.pk)
        elif action == "item_delete" and menu:
            MenuItem.objects.filter(pk=request.POST.get("pk"), menu=menu).delete()
            return redirect("website:menu", menu.pk)
        elif action == "reorder" and menu:
            try:
                order = json.loads(request.POST.get("order", "[]"))
            except ValueError:
                order = []
            for i, row in enumerate(order):
                MenuItem.objects.filter(pk=row.get("id"), menu=menu).update(order=i, parent_id=row.get("parent") or None)
            return JsonResponse({"ok": True})
    return render(request, "website/menus.html", {
        "menus": all_menus, "menu": menu, "tree": menu.tree() if menu else [], "mform": mform, "iform": iform,
        "pages": Page.objects.filter(status="published"),
    })


@require("website")
def brand(request):
    form = BrandForm(request.POST or None, request.FILES or None, instance=Brand.load())
    if request.method == "POST" and form.is_valid():
        form.save()
        log_activity(request, "update", "Restaurant brand changed", "website")
        messages.success(request, _("Brand saved."))
        return redirect("website:brand")
    return render(request, "website/brand.html", {"form": form})


@require("website")
def seo(request):
    form = SEOForm(request.POST or None, request.FILES or None, instance=SEOSettings.load())
    if request.method == "POST" and form.is_valid():
        form.save()
        log_activity(request, "update", "SEO settings changed", "website")
        messages.success(request, _("SEO settings saved."))
        return redirect("website:seo")
    issues = []
    for p in Page.objects.filter(status="published"):
        text = builder.layout_text(p.layout) if p.editor == Page.Editor.BUILDER else p.content
        if not (p.meta_description or p.excerpt):
            issues.append((p, _("No meta description")))
        if len(p.meta_title or p.title) > 60:
            issues.append((p, _("Title longer than 60 characters")))
        if not p.focus_keyword:
            issues.append((p, _("No focus keyword")))
        elif p.focus_keyword.lower() not in (p.meta_title or p.title).lower():
            issues.append((p, _("The focus keyword is not in the SEO title")))
        if len((text or "").split()) < 80:
            issues.append((p, _("Little text (less than 80 words)")))
    return render(request, "website/seo.html", {"form": form, "issues": issues, "brand": Brand.load()})


@require("website")
def media(request):
    form = MediaForm()
    if request.method == "POST":
        form = MediaForm(request.POST, request.FILES)
        if form.is_valid():
            m = form.save(commit=False)
            m.uploaded_by = request.user
            m.title = m.title or m.file.name.rsplit("/", 1)[-1]
            m.save()
            log_activity(request, "upload", f"Media '{m.title}' uploaded", "website")
            if request.headers.get("x-requested-with") == "fetch":
                return JsonResponse({"url": m.file.url, "id": m.pk})
            messages.success(request, _("File uploaded."))
            return redirect("website:media")
        if request.headers.get("x-requested-with") == "fetch":
            return JsonResponse({"error": " ".join(" ".join(v) for v in form.errors.values())}, status=400)
    files = Paginator(MediaFile.objects.all(), 48).get_page(request.GET.get("page"))
    if request.GET.get("format") == "json":
        return JsonResponse({"files": [{"url": f.file.url, "title": f.title, "alt": f.alt, "image": f.is_image} for f in files]})
    return render(request, "website/media.html", {"form": form, "page": files})


@require("website")
@require_POST
def media_delete(request, pk):
    m = get_object_or_404(MediaFile, pk=pk)
    m.file.delete(save=False)
    m.delete()
    messages.success(request, _("File deleted."))
    return redirect("website:media")


# ================================================================ public site

def site_ctx(request, page=None):
    seo_cfg = SEOSettings.load()
    brand_obj = Brand.load()
    look = Appearance.load()
    header = Menu.objects.filter(location=Menu.Location.HEADER).first()
    footer = Menu.objects.filter(location=Menu.Location.FOOTER).first()
    site_title = seo_cfg.site_title or brand_obj.name
    if page and not page.is_homepage:
        title = page.meta_title or f"{page.title} {seo_cfg.title_separator} {site_title}"
    else:
        title = (page.meta_title if page and page.meta_title else None) or (
            f"{site_title} {seo_cfg.title_separator} {brand_obj.motto}" if brand_obj.motto else site_title)
    base = (seo_cfg.canonical_domain or request.build_absolute_uri("/")).rstrip("/")
    canonical = base + (page.get_absolute_url() if page else request.path)
    og_image = None
    for img in (page and page.og_image, page and page.featured_image, seo_cfg.default_og_image, look.hero_image, brand_obj.logo):
        if img:
            og_image = base + img.url
            break
    schema = {
        "@context": "https://schema.org", "@type": seo_cfg.schema_type, "name": brand_obj.name, "url": base + "/",
        "address": {"@type": "PostalAddress", "streetAddress": brand_obj.address, "addressLocality": brand_obj.city,
                    "addressCountry": brand_obj.country},
        "acceptsReservations": "True",
    }
    if brand_obj.cuisine:
        schema["servesCuisine"] = [c.strip() for c in brand_obj.cuisine.split(",") if c.strip()]
    if brand_obj.price_range:
        schema["priceRange"] = brand_obj.price_range
    if brand_obj.phone:
        schema["telephone"] = brand_obj.phone
    if brand_obj.email:
        schema["email"] = brand_obj.email
    if brand_obj.logo:
        schema["logo"] = schema["image"] = base + brand_obj.logo.url
    if brand_obj.socials:
        schema["sameAs"] = [u for _n, u in brand_obj.socials]
    try:
        from pos.models import PosSettings

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        spec = []
        for d, h in PosSettings.load().hours.items():
            if h and len(h) == 2 and str(d).isdigit() and int(d) < 7:
                spec.append({"@type": "OpeningHoursSpecification", "dayOfWeek": days[int(d)], "opens": h[0], "closes": h[1]})
        if spec:
            schema["openingHoursSpecification"] = spec
    except Exception:  # noqa: BLE001
        pass
    if seo_cfg.schema_type == "Organization":
        # A company website (e.g. the software vendor): no restaurant details.
        schema = {k: v for k, v in schema.items() if k not in (
            "servesCuisine", "priceRange", "acceptsReservations", "openingHoursSpecification")}
    graph = [schema]
    if seo_cfg.breadcrumbs and page and not page.is_homepage:
        crumbs = [{"@type": "ListItem", "position": 1, "name": brand_obj.name, "item": base + "/"}]
        if page.parent:
            crumbs.append({"@type": "ListItem", "position": 2, "name": page.parent.title, "item": base + page.parent.get_absolute_url()})
        crumbs.append({"@type": "ListItem", "position": len(crumbs) + 1, "name": page.title, "item": canonical})
        graph.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": crumbs})
    ctx = {
        "page": page, "seo": seo_cfg, "look": look, "brand": brand_obj, "header_menu": header.tree() if header else [],
        "footer_menu": footer.tree() if footer else [],
        "meta_title": title,
        "meta_description": (page.meta_description or page.excerpt if page else "") or seo_cfg.meta_description or brand_obj.motto,
        "canonical": canonical, "og_image": og_image,
        "noindex": not seo_cfg.allow_indexing or (page is not None and page.noindex),
        "schema_json": json.dumps(graph if len(graph) > 1 else schema, ensure_ascii=False).replace("</", "<\\/"),
        "theme_template": f"website/themes/{look.theme}.html",
        "sys": SystemSettings.load(),
        "demo_site": getattr(request, "demo_site", False),
    }
    if ctx["demo_site"]:
        ctx["noindex"] = True
    from core.i18n import get_language

    ctx["lang"] = get_language()
    menu = ctx["header_menu"]
    half = (len(menu) + 1) // 2
    ctx["header_left"], ctx["header_right"] = menu[:half], menu[half:]
    ctx["footer_html"] = builder.render_layout(look.footer_layout, ctx) if look.footer_layout else ""
    if page is not None and page.editor == Page.Editor.BUILDER:
        ctx["body_html"] = builder.render_layout(page.layout, ctx)
        first = next(iter((page.layout or {}).get("sections", [])), None)
        first_w = next((c["widgets"][0] for c in (first or {}).get("columns", []) if c.get("widgets")), None)
        ctx["starts_with_hero"] = bool(first_w and first_w.get("type") == "hero")
    hero_on_top = (page is None or page.is_homepage or page.template == Page.Template.LANDING) and look.hero_enabled
    ctx["over_hero"] = look.theme == "modern" and (hero_on_top or ctx.get("starts_with_hero"))
    return ctx


def _maintenance(request):
    s = SystemSettings.load()
    if s.maintenance_mode and not (request.user.is_authenticated and request.user.is_system):
        return render(request, "website/maintenance.html", {"message": s.maintenance_message}, status=503)
    return None


def _redirect(request):
    target = SEOSettings.load().redirect_map().get(request.path.rstrip("/") or "/")
    return redirect(target, permanent=True) if target else None


def home(request):
    if (resp := _maintenance(request)) is not None:
        return resp
    page = Page.objects.filter(is_homepage=True, status="published").first()
    ctx = site_ctx(request, page)
    ctx["is_home"] = True
    return render(request, ctx["theme_template"], ctx)


def page_view(request, slug):
    if (resp := _maintenance(request)) is not None:
        return resp
    page = Page.objects.filter(slug=slug).first()
    preview = request.user.is_authenticated and request.GET.get("preview") and page is not None
    if page is None or (page.status != Page.Status.PUBLISHED and not preview):
        if (resp := _redirect(request)) is not None:
            return resp
        raise Http404
    if page.is_homepage:
        return redirect("/", permanent=True)
    ctx = site_ctx(request, page)
    ctx["children"] = page.children.filter(status="published")
    resp = render(request, ctx["theme_template"], ctx)
    if preview:
        resp["Cache-Control"] = "private, no-store"
    return resp


def not_found(request, exception=None):
    if (resp := _redirect(request)) is not None:
        return resp
    try:
        ctx = site_ctx(request)
        ctx["not_found"] = True
        return render(request, ctx["theme_template"], ctx, status=404)
    except Exception:  # noqa: BLE001
        return HttpResponse("<h1>404</h1>", status=404)


def robots_txt(request):
    s = SEOSettings.load()
    base = (s.canonical_domain or request.build_absolute_uri("/")).rstrip("/")
    lines = ["User-agent: *"]
    if s.allow_indexing:
        lines += ["Disallow: /dashboard/", "Disallow: /login/", "Disallow: /demo/", "Allow: /"]
    else:
        lines.append("Disallow: /")
    if s.robots_extra:
        lines += [ln for ln in s.robots_extra.splitlines() if ln.strip()]
    if s.sitemap_enabled and s.allow_indexing:
        lines.append(f"Sitemap: {base}/sitemap.xml")
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def sitemap_xml(request):
    s = SEOSettings.load()
    if not s.sitemap_enabled:
        raise Http404
    base = (s.canonical_domain or request.build_absolute_uri("/")).rstrip("/")
    urls = []
    has_home = False
    for p in Page.objects.filter(status="published", noindex=False):
        has_home = has_home or p.is_homepage
        urls.append((base + p.get_absolute_url(), p.updated_at, "1.0" if p.is_homepage else "0.8"))
    if not has_home:
        urls.insert(0, (base + "/", None, "1.0"))
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, mod, prio in urls:
        body.append(f"<url><loc>{loc}</loc>" + (f"<lastmod>{mod:%Y-%m-%d}</lastmod>" if mod else "") + f"<priority>{prio}</priority></url>")
    body.append("</urlset>")
    return HttpResponse("\n".join(body), content_type="application/xml")


# ================================================================ online reservations

def _res_settings():
    from pos.models import PosSettings

    s = PosSettings.load()
    if not s.online_reservations:
        raise Http404
    return s


def booking_slots(request):
    """Free time slots for a date and number of guests (JSON for the reservation widget)."""
    from pos import services

    s = _res_settings()
    try:
        day = date.fromisoformat(request.GET.get("date", ""))
        guests = max(1, min(int(request.GET.get("guests") or 2), s.max_guests_online))
    except ValueError:
        return JsonResponse({"slots": [], "error": _("Choose a date.")})
    slots = services.online_slots(day, guests, s)
    resp = JsonResponse({"slots": slots, "closed": services.opening_window(day, s) is None})
    resp["Cache-Control"] = "no-store"
    return resp


@csrf_exempt  # public form on cached pages; protected by a honeypot, a time check and a rate limit
@require_POST
def book(request):
    from pos import services
    from pos.models import Customer, Reservation

    s = _res_settings()

    def fail(msg, status=400):
        return JsonResponse({"ok": False, "error": msg}, status=status)

    p = request.POST
    if p.get("website"):  # honeypot field, hidden for people
        return JsonResponse({"ok": True, "message": _("Thank you!")})
    ip = client_ip(request)
    recent = ActivityLog.objects.filter(area="booking", ip=ip, created_at__gte=timezone.now() - timedelta(hours=1)).count() if ip else 0
    if recent >= 5:
        return fail(_("Too many reservations from your connection. Please call us."), 429)
    first, last = p.get("first_name", "").strip()[:80], p.get("last_name", "").strip()[:80]
    email, phone = p.get("email", "").strip().lower()[:254], p.get("phone", "").strip()[:40]
    if not (first and last and email and "@" in email):
        return fail(_("Fill in your first name, last name and e-mail address."))
    try:
        day = date.fromisoformat(p.get("date", ""))
        hh, mm = [int(x) for x in p.get("time", "").split(":")]
        guests = int(p.get("guests") or 2)
    except ValueError:
        return fail(_("Choose a date, time and number of guests."))
    if not 1 <= guests <= s.max_guests_online:
        return fail(_("For groups larger than {0} please call us.").format(s.max_guests_online))
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()).replace(hour=hh, minute=mm))
    if start < timezone.now() + timedelta(hours=s.min_hours_ahead):
        return fail(_("Online reservations must be made at least {0} hours in advance.").format(s.min_hours_ahead))
    if day > timezone.localdate() + timedelta(days=s.max_days_ahead):
        return fail(_("You can book up to {0} days ahead.").format(s.max_days_ahead))
    if timezone.localtime(start).strftime("%H:%M") not in {x["time"] for x in services.online_slots(day, guests, s) if x["free"]}:
        return fail(_("Sorry, this time is no longer available. Please choose another time."))
    with transaction.atomic():
        table = services.find_table(start, guests, online=True, s=s)
        if table is None:
            return fail(_("Sorry, this time is no longer available. Please choose another time."))
        customer = Customer.objects.filter(email__iexact=email).first()
        if customer is None:
            customer = Customer.objects.create(first_name=first, last_name=last, email=email, phone=phone,
                                               marketing=bool(p.get("marketing")))
        elif phone and not customer.phone:
            customer.phone = phone
            customer.save(update_fields=["phone"])
        r = Reservation.objects.create(
            customer=customer, table=table, start=start, duration_minutes=s.dining_minutes, guests=guests,
            status=Reservation.Status.CONFIRMED if s.auto_confirm else Reservation.Status.PENDING,
            source=Reservation.Source.WEBSITE, notes=p.get("notes", "").strip()[:500],
        )
    services.bump()
    ActivityLog.objects.create(kind="create", area="booking", message=f"Online reservation {r}"[:255], ip=ip)
    from core.models import Role, User
    from core.utils import notify, send_system_mail

    staff = User.objects.filter(role__in=(Role.MANAGER, Role.OWNER), is_active=True)
    notify(staff, "New online reservation: {0}", message=f"{customer} · {guests} · {timezone.localtime(start):%d-%m %H:%M}",
           link="/dashboard/pos/reservations/?date=" + day.isoformat(), category="reservation", args=(str(customer),), email=False)
    brand = Brand.load()
    when = timezone.localtime(start).strftime("%d-%m-%Y %H:%M")
    send_system_mail([customer.email], f"{brand.name}: {_('Reservation')} {when}",
                     _("Dear {0},\n\nThank you for your reservation for {1} guests on {2}.\n\n{3}").format(
                         customer.first_name, guests, when, brand.contact_line))
    msg = (_("Thank you, {0}! Your table for {1} on {2} is confirmed.") if r.status == Reservation.Status.CONFIRMED
           else _("Thank you, {0}! We received your request for {1} on {2} and will confirm it soon.")).format(first, guests, when)
    return JsonResponse({"ok": True, "message": msg})
