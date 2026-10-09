"""The installable app (PWA) for tablets and phones.

On Android (Chrome / Edge) the system can be installed from the browser: it
then opens full screen from its own icon, like a normal app. It is the same
system, so everything stays in sync. /app/ is the start screen: log in to the
restaurant, or try the demo.
"""
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control

from . import demo
from .context_processors import system_version
from .i18n import _
from .models import SystemSettings


@cache_control(max_age=3600, public=True)
def manifest(request):
    name = SystemSettings.load().system_name
    icons = [
        {"src": static("odg/img/app/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": static("odg/img/app/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": static("odg/img/app/maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ]
    data = {
        "id": "/app/",
        "name": name,
        "short_name": "ODG POS",
        "description": _("Restaurant POS, kitchen, bar, Cassa and reservations — synchronised in real time."),
        "start_url": "/app/?source=app",
        "scope": "/",
        "display": "standalone",
        "display_override": ["standalone", "fullscreen"],
        "orientation": "any",
        "background_color": "#0d1530",
        "theme_color": "#0d1530",
        "lang": "en",
        "categories": ["business", "food", "productivity"],
        "icons": icons,
        "shortcuts": [
            {"name": _("Take orders"), "url": "/dashboard/pos/", "icons": [icons[0]]},
            {"name": _("Kitchen"), "url": "/dashboard/pos/kitchen/", "icons": [icons[0]]},
            {"name": _("Bar"), "url": "/dashboard/pos/bar/", "icons": [icons[0]]},
            {"name": _("Cassa"), "url": "/dashboard/pos/cassa/", "icons": [icons[0]]},
        ],
    }
    return JsonResponse(data, content_type="application/manifest+json")


def service_worker(request):
    """Served from the root so it may control the whole site."""
    body = (settings.BASE_DIR / "static" / "odg" / "js" / "sw.js").read_text(encoding="utf-8")
    body = body.replace("__VERSION__", system_version()).replace("__OFFLINE__", "/app/offline/")
    resp = HttpResponse(body, content_type="application/javascript")
    resp["Cache-Control"] = "no-cache"
    resp["Service-Worker-Allowed"] = "/"
    return resp


def app_home(request):
    """App start screen. Logged-in staff go straight to their dashboard."""
    if request.user.is_authenticated and request.GET.get("source") != "switch":
        return redirect("core:dashboard")
    return render(request, "core/app.html", {
        "demo_on": SystemSettings.load().demo_enabled,
        "current": demo.find_for_visitor(request) if SystemSettings.load().demo_enabled else None,
        "roles": demo.ROLES,
    })


def offline(request):
    return render(request, "core/offline.html")
