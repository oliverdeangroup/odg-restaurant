"""Who can open which dashboard tab.

Administrator: everything except running the live Cassa (only Manager and
Owner take payments); the administrator manages Cassa settings and history.
Moderator: like the administrator, without Updates, System users and Settings.
Owner: full restaurant overview, finance, live POS, Cassa, floor, reservations.
Manager: live POS + Cassa, all orders, floor, reservations, limited history,
staff performance. Waiter / Bartender / Chef: their own live screens.
"""
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import Role

ALL = {
    "home", "activity", "updates", "settings", "pos_settings",
    "pos_waiter", "pos_bar", "pos_kitchen", "pos_overview",
    "cassa", "cassa_pay", "history", "products", "floor", "floor_design",
    "reservations", "customers", "performance",
    "finance", "website", "users_system", "users_staff",
}

ROLE_PERMS = {
    Role.ADMIN: ALL - {"cassa_pay"},
    Role.MODERATOR: {
        "home", "pos_overview", "cassa", "history", "products", "floor", "floor_design", "reservations",
        "customers", "performance", "website", "users_staff", "pos_bar", "pos_kitchen",
    },
    Role.OWNER: {
        "home", "pos_waiter", "pos_bar", "pos_kitchen", "pos_overview", "cassa", "cassa_pay", "history",
        "products", "floor", "floor_design", "reservations", "customers", "performance", "finance",
    },
    Role.MANAGER: {
        "home", "pos_waiter", "pos_bar", "pos_kitchen", "pos_overview", "cassa", "cassa_pay", "history",
        "products", "floor", "floor_design", "reservations", "customers", "performance",
    },
    Role.WAITER: {"home", "pos_waiter", "floor"},
    Role.BARTENDER: {"home", "pos_bar", "floor"},
    Role.CHEF: {"home", "pos_kitchen", "floor"},
}


def perms_for(user):
    if not user.is_authenticated or not user.is_active:
        return set()
    if user.is_superuser:
        return ROLE_PERMS[Role.ADMIN]
    return ROLE_PERMS.get(user.role, set())


def can(user, perm):
    return perm in perms_for(user)


def history_days(user):
    """How far back a user may look in the order history."""
    from pos.models import PosSettings

    s = PosSettings.load()
    if user.role == Role.MANAGER:
        return min(s.manager_history_days, s.order_history_days)
    return s.order_history_days


def require(*perm_list):
    """@require("cassa") or @require("pos_bar", "pos_kitchen") (any of them)."""

    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"/login/?next={request.path}")
            perms = perms_for(request.user)
            if not any(p in perms for p in perm_list):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return deco
