"""Public demo: landing page, start / resume with a code, switch role, reset and exit,
and the website of the demo restaurant (Dinosaur BBQ)."""
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import demo
from .i18n import _
from .models import DemoSandbox, SystemSettings, User
from .utils import client_ip

ENTER_URL = "/dashboard/demo/enter/"

# Where each demo role starts.
START_URLS = {
    "waiter": "/dashboard/pos/",
    "bartender": "/dashboard/pos/bar/",
    "chef": "/dashboard/pos/kitchen/",
    "manager": "/dashboard/pos/overview/",
    "owner": "/dashboard/home/",
}


def _enabled():
    if not SystemSettings.load().demo_enabled:
        raise Http404


def landing(request):
    """The demo page, in the design of the public website."""
    from website.views import site_ctx

    _enabled()
    ctx = site_ctx(request)
    ctx.update({
        "current": demo.find_for_visitor(request), "expired": request.GET.get("expired"),
        "error": request.GET.get("error"), "hours": demo.HOURS_IDLE, "roles": demo.ROLES,
        "meta_title": f"{_('Live demo')} | {ctx['brand'].name}", "noindex": False,
        "meta_description": _("Try the restaurant system as waiter, bartender, chef, manager or owner. No login needed: you get your own private demo restaurant."),
    })
    return render(request, "core/demo.html", ctx)


@require_POST
def start(request, role):
    _enabled()
    if role not in demo.ROLES:
        raise Http404
    sb = demo.find_for_visitor(request)
    if sb is None:
        ip = client_ip(request)
        recent = DemoSandbox.objects.filter(ip=ip, created_at__gte=timezone.now() - timedelta(hours=1)).count() if ip else 0
        if recent >= demo.MAX_NEW_PER_IP_HOUR:
            return redirect("/demo/?error=limit")
        sb = demo.create_sandbox(role, ip)
    return demo.set_cookie(redirect(f"{ENTER_URL}?as={role}"), sb.code)


@require_POST
def resume(request):
    _enabled()
    code = request.POST.get("code", "").strip().upper().replace(" ", "")
    if code and "-" not in code and len(code) == 8:
        code = f"{code[0]}-{code[1:]}"
    sb = DemoSandbox.objects.filter(code=code).first()
    if sb is None or sb.is_expired or not (demo.sandbox_dir(sb.code) / "db.sqlite3").exists():
        return redirect("/demo/?error=code")
    return demo.set_cookie(redirect(ENTER_URL), sb.code)


def enter(request):
    """Runs inside the demo copy (see DemoMiddleware): logs in as a demo role."""
    if request.demo is None:
        return redirect("/demo/")
    role = request.GET.get("as")
    if role not in demo.ROLES:
        current = request.user.role if request.user.is_authenticated else None
        role = current if current in demo.ROLES else request.demo.role
    if role not in demo.ROLES:
        role = "waiter"
    user = User.objects.filter(username=demo.DEMO_USERNAMES[role]).first()
    if user is None:
        return redirect("/demo/?error=code")
    lang = request.session.get("lang")
    login(request, user, backend="core.auth.UsernameOrEmailBackend")
    if lang:
        request.session["lang"] = lang
    return redirect(START_URLS[role])


@require_POST
def reset(request):
    sb = demo.find_for_visitor(request)
    if sb is not None:
        demo.reset_sandbox(sb)
        return demo.set_cookie(redirect(ENTER_URL), sb.code)
    return redirect("/demo/")


def exit_demo(request):
    resp = redirect("/demo/")
    resp.delete_cookie(demo.COOKIE)
    resp.delete_cookie(settings.SESSION_COOKIE_NAME)
    return resp


# ------------------------------------------------------------------ demo restaurant website

SITE = "/demo/site/"
# Links on the demo website are written for "/"; inside the demo they live under /demo/site/.
_LINK = re.compile(r'((?:href|action|data-slots)=")/(?!/|static/|media/|demo/|dashboard|login|logout)')


def _site(request, view, *args, **kwargs):
    """Runs a public website view inside the visitor's demo copy."""
    _enabled()
    if request.demo is None:
        if request.method != "GET":
            raise Http404
        ip = client_ip(request)
        sb = demo.find_for_visitor(request)
        if sb is None:
            recent = DemoSandbox.objects.filter(ip=ip, created_at__gte=timezone.now() - timedelta(hours=1)).count() if ip else 0
            if recent >= demo.MAX_NEW_PER_IP_HOUR:
                return redirect("/demo/?error=limit")
            sb = demo.create_sandbox("waiter", ip)
        return demo.set_cookie(redirect(request.get_full_path()), sb.code)
    request.demo_site = True
    response = view(request, *args, **kwargs)
    if response.get("Content-Type", "").startswith("text/html") and not response.streaming:
        response.content = _LINK.sub(lambda m: m.group(1) + SITE, response.content.decode("utf-8")).encode("utf-8")
    if response.status_code in (301, 302) and response.get("Location", "").startswith("/") and not response["Location"].startswith("/demo/"):
        response["Location"] = SITE.rstrip("/") + response["Location"]
    return response


def site_home(request):
    from website import views as site

    return _site(request, site.home)


def site_page(request, slug):
    from website import views as site

    return _site(request, site.page_view, slug)


def site_slots(request):
    from website import views as site

    return _site(request, site.booking_slots)


@csrf_exempt
def site_book(request):
    from website import views as site

    return _site(request, site.book)
