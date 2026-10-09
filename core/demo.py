"""Public demo: every visitor gets a private copy of a fully filled demo restaurant.

How it works
* A *template* demo restaurant (SQLite database) is built by `core.demo_seed`
  into DATA_DIR/demo/template/.
* "Start demo" copies that template into DATA_DIR/demo/sandboxes/<code>/ and
  logs the visitor in as the demo waiter, bartender, chef, manager or owner
  *inside that copy*. The visitor can switch role at any time and sees the
  orders move between the dashboards in real time. The administrator
  dashboard is not part of the demo.
* The visitor is recognised by the signed `odg_demo` cookie, and else by IP
  address, so every visitor has one private session ID.
* While a request carries the cookie and goes to the dashboard,
  `DemoMiddleware` activates the copy: the database router sends every query
  there and file storage points at the copy's media folder. The real
  restaurant database and files are never used for that request.
* All times in a fresh copy are moved to "now", so the live queue, today's
  reservations and the finance history always look current.
* Copies expire 24 hours after the last activity and are deleted.
"""
import contextvars
import hashlib
import os
import secrets
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.db import connections
from django.shortcuts import redirect
from django.utils import timezone

COOKIE = "odg_demo"
COOKIE_SALT = "odg-demo"
DEMO_PATHS = ("/dashboard", "/logout/", "/demo/site/")
ROLES = ("waiter", "bartender", "chef", "manager", "owner")
DEMO_USERNAMES = {r: f"demo.{r}" for r in ROLES}
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

HOURS_IDLE = 24          # a copy lives this long after the last click
HOURS_MAX = 72           # and never longer than this
MAX_SANDBOXES = 300      # oldest are removed above this
MAX_NEW_PER_IP_HOUR = 6
TEMPLATE_MAX_AGE = timedelta(days=2)

_state = contextvars.ContextVar("odg_demo_state", default=None)
_build_lock = threading.Lock()


def demo_dir():
    return Path(settings.DATA_DIR) / "demo"


def template_dir():
    return demo_dir() / "template"


def sandbox_dir(code):
    return demo_dir() / "sandboxes" / code


# ------------------------------------------------------------------ context

def active():
    return _state.get()


def media_root():
    st = _state.get()
    return st["media"] if st else None


def _register(alias, db_path, create=False):
    # mode=rw: never create an empty database when a copy is being replaced at that moment.
    name = str(db_path) if create else f"file:{Path(db_path).as_posix()}?mode=rw"
    connections.settings[alias] = {
        "ENGINE": "django.db.backends.sqlite3", "NAME": name, "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True, "CONN_MAX_AGE": 0, "CONN_HEALTH_CHECKS": False, "OPTIONS": {"timeout": 20},
        "TIME_ZONE": None, "USER": "", "PASSWORD": "", "HOST": "", "PORT": "",
        "TEST": {"CHARSET": None, "COLLATION": None, "MIGRATE": True, "MIRROR": None, "NAME": None},
    }


def _unregister(alias):
    try:
        connections[alias].close()
        del connections[alias]
    except Exception:  # noqa: BLE001
        pass
    connections.settings.pop(alias, None)


class use:
    """Context manager: route all ORM queries and uploads to a demo copy."""

    def __init__(self, folder, info=None, create=False):
        self.folder = Path(folder)
        self.alias = "demo_" + hashlib.sha1(str(self.folder).encode()).hexdigest()[:12]
        self.info = info or {}
        self.create = create

    def __enter__(self):
        if self.create:
            (self.folder / "media").mkdir(parents=True, exist_ok=True)
        _register(self.alias, self.folder / "db.sqlite3", self.create)
        self.token = _state.set({"alias": self.alias, "media": self.folder / "media", **self.info})
        return self

    def __exit__(self, *exc):
        _state.reset(self.token)
        _unregister(self.alias)


class DemoRouter:
    """Sends every model to the active demo copy; the sandbox register stays real."""

    def _db(self, model):
        st = _state.get()
        if st is None or model._meta.label == "core.DemoSandbox":
            return "default"
        return st["alias"]

    def db_for_read(self, model, **hints):
        return self._db(model)

    def db_for_write(self, model, **hints):
        return self._db(model)

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True


# ------------------------------------------------------------------ template

def schema_stamp():
    """Changes when the code/database structure changes → copies must be rebuilt."""
    h = hashlib.sha1((settings.BASE_DIR / "VERSION").read_bytes() if (settings.BASE_DIR / "VERSION").exists() else b"")
    for app in ("core", "pos", "finance", "website"):
        for f in sorted((settings.BASE_DIR / app / "migrations").glob("0*.py")):
            h.update(f.name.encode())
    h.update(b"seed-2")  # bump when demo_seed changes
    return h.hexdigest()[:16]


def _template_info():
    stamp_file = template_dir() / "stamp"
    if not (template_dir() / "db.sqlite3").exists() or not stamp_file.exists():
        return None, None
    return stamp_file.read_text().strip(), datetime.fromtimestamp(stamp_file.stat().st_mtime, tz=dt_timezone.utc)


def build_template():
    """Builds a fresh template into a temp folder, then swaps it in."""
    from django.core.management import call_command

    from . import demo_seed

    with _build_lock:
        lock = demo_dir() / "build.lock"
        demo_dir().mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            if time.time() - lock.stat().st_mtime < 600:
                return False  # another worker is building
            lock.unlink(missing_ok=True)
            return build_template()
        try:
            tmp = demo_dir() / f"template-new-{os.getpid()}"
            shutil.rmtree(tmp, ignore_errors=True)
            with use(tmp, create=True) as ctx:
                call_command("migrate", database=ctx.alias, verbosity=0, interactive=False)
                built = demo_seed.seed()
            (tmp / "stamp").write_text(schema_stamp())
            (tmp / "built").write_text(built.isoformat())
            old = demo_dir() / f"template-old-{os.getpid()}"
            if template_dir().exists():
                template_dir().rename(old)
            tmp.rename(template_dir())
            shutil.rmtree(old, ignore_errors=True)
            return True
        finally:
            lock.unlink(missing_ok=True)


def ensure_template():
    stamp, built = _template_info()
    if stamp is None or stamp != schema_stamp():
        build_template()
    elif timezone.now() - built > TEMPLATE_MAX_AGE:
        threading.Thread(target=_safe_build, daemon=True).start()


def _safe_build():
    try:
        build_template()
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("Demo template rebuild failed")
    finally:
        connections.close_all()


# ------------------------------------------------------------------ sandboxes

def new_code():
    return "R-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(7))


def _shift_times(db_path, built_at):
    """Moves every date and time in a fresh copy forward to 'now'."""
    from django.apps import apps

    secs = int((timezone.now() - built_at).total_seconds())
    days = (timezone.localdate() - timezone.localtime(built_at).date()).days
    if secs <= 0:
        return
    con = sqlite3.connect(str(db_path))
    try:
        for app in ("pos", "finance", "core"):
            for model in apps.get_app_config(app).get_models():
                table = model._meta.db_table
                for f in model._meta.concrete_fields:
                    kind = f.get_internal_type()
                    if kind == "DateTimeField":
                        con.execute(
                            f'UPDATE "{table}" SET "{f.column}" = strftime(?, "{f.column}", ?) WHERE "{f.column}" IS NOT NULL',
                            ("%Y-%m-%d %H:%M:%f", f"+{secs} seconds"))
                    elif kind == "DateField" and days:
                        con.execute(f'UPDATE "{table}" SET "{f.column}" = date("{f.column}", ?) WHERE "{f.column}" IS NOT NULL',
                                    (f"+{days} days",))
        # Order codes contain the date and hour (YYYYMMDDHH + table): renumber them.
        rows = con.execute('SELECT id, opened_at, table_number FROM "pos_order" ORDER BY opened_at, id').fetchall()
        con.execute('UPDATE "pos_order" SET code = ? || id', ("tmp",))
        used = set()
        tz = timezone.get_current_timezone()
        for oid, opened, table_number in rows:
            t = datetime.fromisoformat(opened.replace(" ", "T")).replace(tzinfo=dt_timezone.utc).astimezone(tz)
            base = f"{t:%Y%m%d%H}{table_number}"
            code, n = base, 2
            while code in used:
                code, n = f"{base}{n}", n + 1
            used.add(code)
            con.execute('UPDATE "pos_order" SET code = ? WHERE id = ?', (code, oid))
        con.commit()
    finally:
        con.close()


def _copy_template(code):
    """Makes a fresh copy next to the visitor's folder and swaps it in at once,
    so requests that arrive meanwhile (the live screens poll) never see a half copy."""
    target = sandbox_dir(code)
    new = target.with_name(code + ".new")
    shutil.rmtree(new, ignore_errors=True)
    (new / "media").mkdir(parents=True)
    shutil.copy2(template_dir() / "db.sqlite3", new / "db.sqlite3")
    built = template_dir() / "built"
    if built.exists():
        _shift_times(new / "db.sqlite3", datetime.fromisoformat(built.read_text().strip()))
    src_media = template_dir() / "media"
    for root, _dirs, files in os.walk(src_media):
        rel = Path(root).relative_to(src_media)
        (new / "media" / rel).mkdir(parents=True, exist_ok=True)
        for f in files:
            dst = new / "media" / rel / f
            try:
                os.link(Path(root) / f, dst)  # hard link: no extra disk space
            except OSError:
                shutil.copy2(Path(root) / f, dst)
    old = target.with_name(code + ".old")
    shutil.rmtree(old, ignore_errors=True)
    try:
        if target.exists():
            target.rename(old)
        new.rename(target)
    except OSError:
        # Windows (development PC) cannot rename a folder with an open database.
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(new / "db.sqlite3", target / "db.sqlite3")
        shutil.rmtree(new, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)


def create_sandbox(role, ip):
    from .models import DemoSandbox

    cleanup()
    ensure_template()
    code = new_code()
    while DemoSandbox.objects.filter(code=code).exists():
        code = new_code()
    _copy_template(code)
    return DemoSandbox.objects.create(code=code, role=role, ip=ip or None, stamp=schema_stamp())


def reset_sandbox(sb):
    ensure_template()
    _copy_template(sb.code)
    sb.stamp = schema_stamp()
    sb.created_at = sb.last_seen = timezone.now()
    sb.save(update_fields=["stamp", "created_at", "last_seen"])


def delete_sandbox(sb):
    shutil.rmtree(sandbox_dir(sb.code), ignore_errors=True)
    sb.delete()


def cleanup():
    from .models import DemoSandbox

    now = timezone.now()
    old = DemoSandbox.objects.filter(last_seen__lt=now - timedelta(hours=HOURS_IDLE)) | DemoSandbox.objects.filter(
        created_at__lt=now - timedelta(hours=HOURS_MAX))
    for sb in old:
        delete_sandbox(sb)
    extra = DemoSandbox.objects.count() - MAX_SANDBOXES
    if extra > 0:
        for sb in DemoSandbox.objects.order_by("last_seen")[:extra]:
            delete_sandbox(sb)


def find_for_visitor(request):
    """The visitor's copy: from the cookie first, else by IP address."""
    from .models import DemoSandbox
    from .utils import client_ip

    qs = DemoSandbox.objects.filter(last_seen__gte=timezone.now() - timedelta(hours=HOURS_IDLE))
    code = request.get_signed_cookie(COOKIE, default=None, salt=COOKIE_SALT)
    if code:
        sb = qs.filter(code=code).first()
        if sb:
            return sb
    ip = client_ip(request)
    if ip:
        return qs.filter(ip=ip).order_by("-last_seen").first()
    return None


def set_cookie(response, code):
    response.set_signed_cookie(COOKIE, code, salt=COOKIE_SALT, max_age=HOURS_MAX * 3600, httponly=True,
                               secure=not settings.DEBUG, samesite="Lax")
    return response


# ------------------------------------------------------------------ middleware

class DemoMiddleware:
    """Runs the dashboard inside the visitor's demo copy when the demo cookie is set."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.demo = None
        if not request.path.startswith(DEMO_PATHS) or COOKIE not in request.COOKIES:
            return self.get_response(request)
        from .models import DemoSandbox

        code = request.get_signed_cookie(COOKIE, default=None, salt=COOKIE_SALT)
        sb = DemoSandbox.objects.filter(code=code).first() if code else None
        if sb is None or not (sandbox_dir(sb.code) / "db.sqlite3").exists() or sb.is_expired:
            # On the demo website a fresh copy is made right away; the dashboards go back to /demo/.
            resp = redirect(request.path if request.path.startswith("/demo/site/") else "/demo/?expired=1")
            resp.delete_cookie(COOKIE)
            resp.delete_cookie(settings.SESSION_COOKIE_NAME)
            return resp
        if sb.stamp != schema_stamp():
            reset_sandbox(sb)
            return redirect(request.path if request.path.startswith("/demo/site/") else "/dashboard/demo/enter/")
        request.demo = sb
        with use(sandbox_dir(sb.code), {"code": sb.code}):
            response = self.get_response(request)
        if (timezone.now() - sb.last_seen).total_seconds() > 60:
            DemoSandbox.objects.filter(pk=sb.pk).update(last_seen=timezone.now())
        if response.status_code in (301, 302) and response.get("Location", "").startswith("/login"):
            return redirect("/dashboard/demo/enter/")
        response["X-Robots-Tag"] = "noindex"
        return response
