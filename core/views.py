import mimetypes
import platform
import tempfile
from datetime import timedelta
from pathlib import Path

import django
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import updater
from .forms import ProfileForm, StaffUserForm, SystemSettingsForm, SystemUserForm, UpdateUploadForm
from .i18n import _
from .models import STAFF_ROLES, SYSTEM_ROLES, ActivityLog, Notification, Role, SystemSettings, SystemUpdate, User
from .permissions import can, require
from .utils import client_ip, log_activity, random_password


# ------------------------------------------------------------------ auth

def _locked_out(username, ip):
    s = SystemSettings.load()
    since = timezone.now() - timedelta(minutes=s.lockout_minutes)
    fails = ActivityLog.objects.filter(area="login_failed", created_at__gte=since).filter(
        Q(message__iexact=f"Failed login: {username}") | Q(ip=ip)
    ).count()
    return fails >= s.max_login_attempts


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    error = None
    username = ""
    if request.method == "POST":
        from django.contrib.auth import authenticate

        username = request.POST.get("username", "").strip()
        ip = client_ip(request)
        if _locked_out(username, ip):
            error = _("Too many failed attempts. Try again in a few minutes.")
        else:
            user = authenticate(request, username=username, password=request.POST.get("password", ""))
            if user is None:
                ActivityLog.objects.create(kind="login", area="login_failed", message=f"Failed login: {username}"[:255], ip=ip)
                error = _("Wrong username or password.")
            else:
                login(request, user)
                if user.language and "lang" not in request.session:
                    request.session["lang"] = user.language
                log_activity(request, "login", f"{user} logged in", "auth", user=user)
                nxt = request.POST.get("next") or request.GET.get("next")
                if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}):
                    resp = redirect(nxt)
                else:
                    resp = redirect("core:dashboard")
                resp.delete_cookie("odg_demo")  # a real login always leaves the demo
                return resp
    return render(request, "core/login.html", {
        "error": error, "username": username,
        "timeout": request.GET.get("timeout"), "next": request.GET.get("next", ""),
    })


def logout_view(request):
    if getattr(request, "demo", None) is not None:
        logout(request)
        resp = redirect("/demo/")
        resp.delete_cookie("odg_demo")
        return resp
    lang = request.session.get("lang")
    logout(request)
    if lang:
        request.session["lang"] = lang
    return redirect("core:login")


@login_required
def dashboard(request):
    """Everyone starts on their own Home screen."""
    return redirect("core:home")


def forbidden(request, exception=None):
    return render(request, "core/403.html", status=403)


# ------------------------------------------------------------------ home

@require("home")
def home(request):
    """Personalized overview per role: live figures, notifications and quick actions."""
    from pos.home import home_context

    ctx = home_context(request)
    if request.GET.get("partial") == "1":
        return render(request, "core/_home_live.html", ctx)
    return render(request, "core/home.html", ctx)


@require("activity")
def activity(request):
    qs = ActivityLog.objects.select_related("user")
    kind = request.GET.get("kind")
    if kind:
        qs = qs.filter(kind=kind)
    area = request.GET.get("area")
    if area:
        qs = qs.filter(area=area)
    q = request.GET.get("q")
    if q:
        qs = qs.filter(Q(message__icontains=q) | Q(user__username__icontains=q))
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    areas = ActivityLog.objects.exclude(area="").values_list("area", flat=True).distinct().order_by("area")
    return render(request, "core/activity.html", {"page": page, "kinds": ActivityLog.Kind.choices, "areas": areas})


# ------------------------------------------------------------------ updates

@require("updates")
def updates(request):
    form = UpdateUploadForm()
    preview = None
    pending = request.session.get("pending_update")
    if request.method == "POST" and "package" in request.FILES:
        form = UpdateUploadForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data["package"]
            if not f.name.lower().endswith(".zip"):
                messages.error(request, _("Upload a .zip file."))
            else:
                tmp_dir = Path(settings.DATA_DIR) / "updates"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=tmp_dir)
                for chunk in f.chunks():
                    tmp.write(chunk)
                tmp.close()
                try:
                    info = updater.inspect(tmp.name)
                except (updater.UpdateError, Exception) as e:  # noqa: BLE001
                    Path(tmp.name).unlink(missing_ok=True)
                    messages.error(request, f"{_('The package was rejected')}: {e}")
                else:
                    upd = SystemUpdate.objects.create(
                        version=info["version"], previous_version=info["current"], notes=info["notes"],
                        file_name=f.name, uploaded_by=request.user,
                    )
                    request.session["pending_update"] = {"id": upd.pk, "path": tmp.name}
                    log_activity(request, "upload", f"Update package {f.name} uploaded", "updates")
                    return redirect("core:updates")
    if pending:
        try:
            preview = updater.inspect(pending["path"])
            preview["id"] = pending["id"]
            preview["is_older"] = updater.vtuple(preview["version"]) <= updater.vtuple(preview["current"])
        except Exception:  # noqa: BLE001
            request.session.pop("pending_update", None)
    return render(request, "core/updates.html", {
        "form": form, "preview": preview, "history": SystemUpdate.objects.select_related("uploaded_by")[:20],
        "version": updater.current_version(),
        "backups": sorted(Path(settings.BACKUP_DIR).glob("*"), reverse=True)[:10] if Path(settings.BACKUP_DIR).exists() else [],
    })


@require("updates")
@require_POST
def update_apply(request):
    pending = request.session.pop("pending_update", None)
    if not pending:
        return redirect("core:updates")
    upd = get_object_or_404(SystemUpdate, pk=pending["id"])
    if request.POST.get("action") == "cancel":
        Path(pending["path"]).unlink(missing_ok=True)
        upd.status = SystemUpdate.Status.ROLLED_BACK
        upd.log = "Cancelled before installing."
        upd.save()
        return redirect("core:updates")
    try:
        ok, log = updater.apply(upd, pending["path"], allow_destructive=bool(request.POST.get("allow_destructive")))
    except updater.UpdateError as e:
        ok, log = False, str(e)
    except Exception as e:  # noqa: BLE001
        ok, log = False, f"Unexpected error: {e}"
    upd.status = SystemUpdate.Status.APPLIED if ok else SystemUpdate.Status.FAILED
    upd.log = log
    upd.save()
    Path(pending["path"]).unlink(missing_ok=True)
    log_activity(request, "system", f"Update {upd.version} {'applied' if ok else 'failed'}", "updates")
    if ok:
        messages.success(request, _("Update {0} installed. All data was kept.").format(upd.version))
    else:
        messages.error(request, _("The update failed. Nothing was changed. See the log below."))
    return redirect("core:updates")


@require("updates")
def backup_download(request, name):
    path = (Path(settings.BACKUP_DIR) / name).resolve()
    if path.parent != Path(settings.BACKUP_DIR).resolve() or not path.is_file():
        raise Http404
    log_activity(request, "download", f"Backup {name} downloaded", "updates")
    return FileResponse(open(path, "rb"), as_attachment=True, filename=name)


@require("settings")
@require_POST
def backup_now(request):
    data_file, code_file = updater.backup("manual")
    log_activity(request, "system", "Manual backup created", "settings")
    messages.success(request, _("Backup created: {0}").format(data_file.name))
    return redirect(request.POST.get("next") or "core:settings")


# ------------------------------------------------------------------ notifications / profile

@login_required
def notifications(request):
    qs = request.user.notifications.all()
    if request.method == "POST":
        qs.filter(is_read=False).update(is_read=True)
        return redirect("core:notifications")
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "core/notifications.html", {"page": page})


@login_required
def notification_open(request, pk):
    n = get_object_or_404(Notification, pk=pk, recipient=request.user)
    n.is_read = True
    n.save(update_fields=["is_read"])
    return redirect(n.link or "core:notifications")


@login_required
def profile(request):
    form = ProfileForm(instance=request.user)
    pw_form = PasswordChangeForm(request.user)
    for f in pw_form.fields.values():
        f.widget.attrs["class"] = "inp"
    if request.method == "POST":
        if request.demo is not None:
            messages.error(request, _("This is not possible in the demo."))
            return redirect("core:profile")
        if "change_password" in request.POST:
            pw_form = PasswordChangeForm(request.user, request.POST)
            for f in pw_form.fields.values():
                f.widget.attrs["class"] = "inp"
            if pw_form.is_valid():
                pw_form.save()
                update_session_auth_hash(request, pw_form.user)
                log_activity(request, "update", "Changed own password", "profile")
                messages.success(request, _("Your password was changed."))
                return redirect("core:profile")
        else:
            form = ProfileForm(request.POST, request.FILES, instance=request.user)
            if form.is_valid():
                user = form.save()
                if user.language:
                    request.session["lang"] = user.language
                messages.success(request, _("Your profile was saved."))
                return redirect("core:profile")
    return render(request, "core/profile.html", {"form": form, "pw_form": pw_form})


# ------------------------------------------------------------------ users

USER_KINDS = {
    "system": {"perm": "users_system", "roles": SYSTEM_ROLES, "form": SystemUserForm, "title": "System users"},
    "staff": {"perm": "users_staff", "roles": STAFF_ROLES, "form": StaffUserForm, "title": "Users"},
}


def _employee_roles(user):
    """Staff roles, plus administrators and moderators for those who manage system users."""
    roles = list(STAFF_ROLES) if can(user, "users_staff") else []
    if can(user, "users_system"):
        roles += list(SYSTEM_ROLES)
    return roles


def employees(request):
    """Users → Employees: everyone who works with the system, in one list."""
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    roles = _employee_roles(request.user)
    if not roles:
        return forbidden(request)
    cfg = {"title": "Employees", "roles": roles}
    qs = User.objects.filter(role__in=roles)
    if can(request.user, "users_system"):
        qs = User.objects.filter(Q(role__in=roles) | Q(is_superuser=True))
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q)
            | Q(email__icontains=q) | Q(id_number__icontains=q)
        )
    role = request.GET.get("role")
    if role:
        qs = qs.filter(role=role)
    status = request.GET.get("status", "active")
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    s = SystemSettings.load()
    counts = {
        "max_managers": s.max_managers,
        "by_role": [(r.value, r.label, User.objects.filter(role=r, is_active=True).count()) for r in roles],
    }
    page = Paginator(qs.order_by("role", "first_name", "last_name"), 40).get_page(request.GET.get("page"))
    return render(request, "core/users_list.html", {
        "cfg": cfg, "page": page, "q": q, "status": status, "counts": counts, "role": role,
        "role_choices": [(r.value, r.label) for r in roles],
        "kind_of": {r.value: ("system" if r in SYSTEM_ROLES else "staff") for r in Role},
    })


def users_system(request):
    return redirect("/dashboard/users/employees/?role=admin")


def users_staff(request):
    return redirect("core:employees")


def user_edit(request, kind, pk=None):
    cfg = USER_KINDS.get(kind)
    if cfg is None:
        raise Http404
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    if not can(request.user, cfg["perm"]):
        return forbidden(request)
    if pk:
        instance = get_object_or_404(User, pk=pk)
        if kind == "staff" and (instance.role in SYSTEM_ROLES or instance.is_superuser):
            return redirect("core:user_edit", "system", pk)
    else:
        wanted = request.GET.get("role")
        instance = User(role=wanted if wanted in [r.value for r in cfg["roles"]] else cfg["roles"][0])
    if pk and kind != "system" and instance.role not in cfg["roles"]:
        raise Http404
    if instance.is_superuser and not request.user.is_superuser:
        return forbidden(request)
    form = cfg["form"](request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        is_new = not instance.pk
        user = form.save(commit=False)
        generated = None
        if is_new and not form.cleaned_data.get("password"):
            generated = random_password()
            user.set_password(generated)
        user.save()
        log_activity(request, "create" if is_new else "update", f"{'Created' if is_new else 'Updated'} user {user}", "users")
        if generated:
            messages.success(request, _("User {0} created. Temporary password: {1}").format(user.username, generated))
        else:
            messages.success(request, _("{0} was saved.").format(user))
        return redirect("core:employees")
    return render(request, "core/user_form.html", {"kind": kind, "cfg": cfg, "form": form, "obj": instance})


@require_POST
def user_action(request, kind, pk):
    cfg = USER_KINDS.get(kind)
    if cfg is None or not request.user.is_authenticated or not can(request.user, cfg["perm"]):
        return forbidden(request)
    user = get_object_or_404(User, pk=pk)
    if user == request.user or (user.is_superuser and not request.user.is_superuser):
        messages.error(request, _("You cannot change this account."))
        return redirect("core:employees")
    action = request.POST.get("action")
    if action == "toggle":
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        log_activity(request, "update", f"{'Activated' if user.is_active else 'Deactivated'} user {user}", "users")
        messages.success(request, _("{0} is now active.").format(user) if user.is_active else _("{0} is now inactive.").format(user))
    elif action == "reset":
        pw = random_password()
        user.set_password(pw)
        user.save(update_fields=["password"])
        log_activity(request, "update", f"Reset password of {user}", "users")
        messages.success(request, _("New temporary password for {0}: {1}").format(user.username, pw))
    elif action == "delete" and request.user.is_admin:
        if request.POST.get("confirm") != user.username:
            messages.error(request, _("Type the username to confirm deleting."))
        else:
            name = str(user)
            user.delete()
            log_activity(request, "delete", f"Deleted user {name}", "users")
            messages.success(request, _("{0} was deleted.").format(name))
    return redirect("core:employees")


# ------------------------------------------------------------------ settings

@require("settings")
def system_settings(request):
    obj = SystemSettings.load()
    form = SystemSettingsForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if "test_mail" in request.POST:
            from .utils import send_system_mail

            if form.is_valid():
                form.save()
                try:
                    sent = send_system_mail([request.user.email], "ODG-RESTAURANT test", _("Your e-mail settings work."), background=False)
                except Exception as e:  # noqa: BLE001
                    sent = False
                    messages.error(request, str(e))
                if sent:
                    messages.success(request, _("Test e-mail sent to {0}.").format(request.user.email))
                else:
                    messages.error(request, _("Could not send. Check the SMTP settings and your own e-mail address."))
            return redirect("core:settings")
        if form.is_valid():
            form.save()
            log_activity(request, "update", "System settings changed", "settings")
            messages.success(request, _("Settings saved."))
            return redirect("core:settings")
    info = {
        "version": updater.current_version(),
        "python": platform.python_version(),
        "django": django.get_version(),
        "database": connection.vendor,
        "data_dir": settings.DATA_DIR,
    }
    return render(request, "core/settings.html", {"form": form, "info": info})


# ------------------------------------------------------------------ files

def public_media(request, path):
    """Serves uploads under media/public/ (logos, page and product images)."""
    from . import demo

    root_dir = demo.media_root() or settings.MEDIA_ROOT
    full = (Path(root_dir) / "public" / path).resolve()
    root = (Path(root_dir) / "public").resolve()
    if root not in full.parents or not full.is_file():
        raise Http404
    ctype = mimetypes.guess_type(full.name)[0] or "application/octet-stream"
    resp = FileResponse(open(full, "rb"), content_type=ctype)
    resp["Cache-Control"] = "public, max-age=604800"
    if ctype == "image/svg+xml":
        resp["Content-Security-Policy"] = "script-src 'none'"
    return resp


@login_required
def avatar(request, pk):
    u = get_object_or_404(User, pk=pk)
    if not u.photo:
        raise Http404
    ctype = mimetypes.guess_type(u.photo.name)[0] or "image/jpeg"
    resp = FileResponse(u.photo.open("rb"), content_type=ctype)
    resp["Cache-Control"] = "private, max-age=86400"
    return resp
