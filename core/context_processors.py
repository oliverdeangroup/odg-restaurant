from django.conf import settings
from django.utils import timezone

from . import i18n
from .models import SystemSettings
from .nav import build_menu
from .permissions import perms_for

_version = None


def system_version():
    global _version
    if _version is None:
        try:
            _version = (settings.BASE_DIR / "VERSION").read_text().strip()
        except OSError:
            _version = "0.0.0"
    return _version


def odg(request):
    from pos.models import PosSettings
    from website.models import Brand

    from .demo import ROLES

    ctx = {
        "sys": SystemSettings.load(),
        "brand": Brand.load(),
        "lang": i18n.get_language(),
        "languages": i18n.LANGUAGES,
        "odg_version": system_version(),
        "today": timezone.localdate(),
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and request.path.startswith("/dashboard"):
        ctx["nav"] = build_menu(request)
        ctx["perms"] = dict.fromkeys(perms_for(user), True)
        ctx["unread_count"] = user.notifications.filter(is_read=False).count()
        ctx["recent_notifications"] = user.notifications.all()[:8]
        ctx["pos_cfg"] = PosSettings.load()
        if getattr(request, "demo", None) is not None:
            ctx["demo_roles"] = [(r, r.capitalize()) for r in ROLES]
    return ctx
