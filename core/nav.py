"""The left-hand dashboard menu (tabs and sub-tabs), filtered by role."""
from django.urls import reverse

from .permissions import perms_for

# (label, icon, [(sub label, url name, permission)])
MENU = [
    ("Home", "home", [
        ("Home", "core:home", "home"),
    ]),
    ("POS", "pos", [
        ("Live overview", "pos:overview", "pos_overview"),
        ("Take orders", "pos:tables", "pos_waiter"),
        ("Bar", "pos:bar", "pos_bar"),
        ("Kitchen", "pos:kitchen", "pos_kitchen"),
        ("Cassa", "pos:cassa", "cassa"),
        ("Order history", "pos:history", "history"),
        ("Products", "pos:products", "products"),
        ("Floor manager", "pos:floor", "floor"),
        ("Table reservation", "pos:reservations", "reservations"),
        ("Staff performance", "pos:performance", "performance"),
    ]),
    ("Finance", "chart", [
        ("Overview", "finance:overview", "finance"),
        ("PDF report", "finance:report", "finance"),
        ("Expenses", "finance:expenses", "finance"),
        ("Day closes", "pos:day_closes", "finance"),
    ]),
    ("Website", "globe", [
        ("Pages", "website:pages", "website"),
        ("Appearance", "website:appearance", "website"),
        ("Menu", "website:menus", "website"),
        ("Brand", "website:brand", "website"),
        ("SEO", "website:seo", "website"),
        ("Media", "website:media", "website"),
    ]),
    ("Users", "users", [
        ("Employees", "core:employees", "users_staff"),
        ("Customers", "pos:customers", "customers"),
    ]),
    ("Settings", "settings", [
        ("Settings", "core:settings", "settings"),
        ("POS", "pos:settings", "pos_settings"),
        ("Reservations", "pos:reservation_settings", "pos_settings"),
        ("Updates", "core:updates", "updates"),
        ("Activity log", "core:activity", "activity"),
    ]),
]


def build_menu(request):
    perms = perms_for(request.user)
    path = request.path
    tabs = []
    for label, icon, subs in MENU:
        items = []
        for sub_label, url_name, perm in subs:
            if perm not in perms:
                continue
            url = reverse(url_name)
            items.append({"label": sub_label, "url": url, "active": path == url or (path.startswith(url) and url.count("/") > 2)})
        if not items:
            continue
        # The most specific match wins (e.g. /pos/cassa/x/ over /pos/).
        best = max((i for i in items if i["active"]), key=lambda i: len(i["url"]), default=None)
        for i in items:
            i["active"] = i is best
        tabs.append({
            "label": label,
            "icon": icon,
            "url": items[0]["url"],
            "items": items if len(items) > 1 else [],
            "active": best is not None,
        })
    return tabs
