import time

from django.contrib.auth import logout
from django.shortcuts import redirect

from . import i18n
from .models import SystemSettings


class RequestCacheMiddleware:
    """Starts every request with an empty settings cache (see core.models.Singleton)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .models import end_singleton_cache, start_singleton_cache

        token = start_singleton_cache()
        try:
            return self.get_response(request)
        finally:
            end_singleton_cache(token)


class LanguageMiddleware:
    """Picks the UI language: ?lang= > session > user profile > system default.

    Runs before authentication, so the user's own preference is applied
    lazily in `core.context_processors` / `SessionTimeoutMiddleware`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = request.GET.get("lang")
        if lang in i18n.LANG_CODES:
            request.session["lang"] = lang
        lang = request.session.get("lang") or SystemSettings.load().default_language
        i18n.set_language(lang)
        request.lang = lang
        return self.get_response(request)


class NoCacheMiddleware:
    """Stops NGINX/LiteSpeed/browser caches from keeping private pages.

    The server has cPanel's NGINX cache in front of LiteSpeed: without this a
    logged-in page (grades, mail) could be cached and shown to someone else.
    """

    PRIVATE_PREFIXES = ("/dashboard", "/login", "/logout", "/media/private")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if request.path.startswith(self.PRIVATE_PREFIXES) or (user is not None and user.is_authenticated):
            response["Cache-Control"] = "private, no-store, no-cache, max-age=0, must-revalidate"
            response["Pragma"] = "no-cache"
            response["X-Accel-Expires"] = "0"  # tells NGINX not to cache
        elif "Cache-Control" not in response and request.method == "GET":
            # Pages depend on the visitor's language and on live data (free
            # reservation times), so NGINX must not keep a copy.
            if response.get("Content-Type", "").startswith("text/html"):
                response["Cache-Control"] = "no-cache"
                response["X-Accel-Expires"] = "0"
            else:
                response["Cache-Control"] = "public, max-age=300"
        return response


class SessionTimeoutMiddleware:
    """Applies the user's language and logs out idle users (Settings → Security)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            if "lang" not in request.session and user.language in i18n.LANG_CODES:
                i18n.set_language(user.language)
                request.lang = user.language
            now = int(time.time())
            last = request.session.get("last_seen", now)
            limit = SystemSettings.load().session_timeout_minutes * 60
            if limit and now - last > limit:
                lang = request.session.get("lang")
                logout(request)
                if lang:
                    request.session["lang"] = lang
                return redirect(f"/login/?timeout=1&next={request.path}")
            request.session["last_seen"] = now
        return self.get_response(request)
