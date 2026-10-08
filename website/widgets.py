"""Extra data for builder widgets that show live restaurant data."""
import re
from datetime import timedelta
from urllib.parse import quote_plus

from django.utils import timezone

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def menu_tree(category_ids=None):
    """Website menu: categories (with sub-categories) and their products."""
    from pos.models import Category, Product

    cats = list(Category.objects.filter(active=True, show_on_website=True))
    prods = {}
    for p in Product.objects.filter(active=True, show_on_website=True, category__in=cats):
        prods.setdefault(p.category_id, []).append(p)
    by_parent = {}
    for c in cats:
        by_parent.setdefault(c.parent_id, []).append(c)

    def build(c, depth):
        kids = [build(k, depth + 1) for k in by_parent.get(c.pk, [])]
        kids = [k for k in kids if k["products"] or k["children"]]
        return {"c": c, "products": prods.get(c.pk, []), "children": kids, "depth": depth}

    if category_ids:
        roots = [c for c in cats if c.pk in category_ids]
    else:
        roots = by_parent.get(None, [])
    out = [build(c, 0) for c in roots]
    return [n for n in out if n["products"] or n["children"]]


def hours_rows():
    from pos.models import PosSettings

    s = PosSettings.load()
    rows = []
    for d, name in enumerate(WEEKDAYS):
        h = s.hours.get(str(d)) or []
        rows.append({"day": name, "open": h[0] if h else "", "close": h[1] if h else "", "today": d == timezone.localdate().weekday()})
    return rows


def map_src(query, brand):
    q = (query or "").strip()
    if q.startswith("https://www.google.com/maps/embed"):
        return q
    if not q:
        if brand.map_embed_url:
            return brand.map_embed_url
        q = ", ".join(p for p in (brand.name, brand.address, brand.city, brand.country) if p)
    return f"https://www.google.com/maps?q={quote_plus(q)}&output=embed"


def video_src(url):
    url = url or ""
    m = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([\w-]{6,20})", url)
    if m:
        return f"https://www.youtube-nocookie.com/embed/{m.group(1)}"
    m = re.search(r"vimeo\.com/(?:video/)?(\d+)", url)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}"
    return ""


def widget_context(w, ctx):
    t = w.get("type")
    d = w.get("data", {})
    if t == "menu":
        return {"tree": menu_tree(d.get("categories"))}
    if t in ("hours", "contact"):
        return {"hours": hours_rows()}
    if t == "map":
        return {"map_src": map_src(d.get("query"), ctx["brand"])}
    if t == "video":
        return {"video_src": video_src(d.get("url"))}
    if t == "reservation":
        from pos.models import PosSettings

        s = PosSettings.load()
        today = timezone.localdate()
        return {"rs": s, "min_date": today.isoformat(), "max_date": (today + timedelta(days=s.max_days_ahead)).isoformat(),
                "guest_range": range(1, s.max_guests_online + 1)}
    return {}
