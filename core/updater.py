"""System updates from a ZIP package (Dashboard → Updates).

Why user data is safe during an update:
* All uploads and backups live in DATA_DIR (outside the code). The updater
  refuses to write there, or to .env / the virtualenv / the SQLite file.
* Before anything changes, a full data export (JSON) and a copy of the
  current code are written to DATA_DIR/backups.
* Database changes only happen through Django migrations. A package whose
  migrations would delete a table or column is blocked unless the admin
  explicitly confirms it.
* If migrating fails, the previous code is restored automatically.

Package layout: the project files plus `odg_update.json` at the root:
    {"version": "1.1.0", "notes": "What changed", "delete": ["old/file.py"]}
Build one with:  python manage.py make_update 1.1.0 --notes "..."
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

MANIFEST = "odg_update.json"
PROTECTED_TOP = {
    ".env", "data", ".venv", "venv", "staticfiles", "run", "db.sqlite3", ".git", "dist", "backups", "logs",
    # development-only files that must never travel in an update package
    ".claude", "DEV-LOGINS.txt", "RESTAURANT MANAGEMENT SYSTEM.docx",
}
SKIP_PARTS = {"__pycache__", ".DS_Store"}
DESTRUCTIVE = re.compile(r"migrations\.(DeleteModel|RemoveField|RemoveConstraint|RemoveIndex)\(")


class UpdateError(Exception):
    pass


def current_version():
    try:
        return (settings.BASE_DIR / "VERSION").read_text().strip()
    except OSError:
        return "0.0.0"


def vtuple(v):
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.\-]", v)[:3])


def _members(zf):
    """Returns (prefix, manifest dict). Accepts a single wrapping folder."""
    names = zf.namelist()
    if MANIFEST in names:
        prefix = ""
    else:
        candidates = [n for n in names if n.endswith("/" + MANIFEST) and n.count("/") == 1]
        if not candidates:
            raise UpdateError("This ZIP is not an ODG-RESTAURANT update package (odg_update.json is missing).")
        prefix = candidates[0][: -len(MANIFEST)]
    try:
        manifest = json.loads(zf.read(prefix + MANIFEST).decode("utf-8"))
    except (ValueError, KeyError) as e:
        raise UpdateError(f"odg_update.json is not valid: {e}") from e
    if not manifest.get("version"):
        raise UpdateError("odg_update.json has no version number.")
    return prefix, manifest


def _safe_rel(name, prefix):
    rel = name[len(prefix):]
    if not rel or rel.endswith("/"):
        return None
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts or "\\" in rel or ":" in p.parts[0]:
        raise UpdateError(f"Unsafe path in package: {rel}")
    if p.parts[0] in PROTECTED_TOP or SKIP_PARTS & set(p.parts) or rel == MANIFEST:
        return None
    return p


def inspect(zip_path):
    """Validates a package and reports what it would do."""
    with zipfile.ZipFile(zip_path) as zf:
        prefix, manifest = _members(zf)
        files, destructive = [], []
        for name in zf.namelist():
            rel = _safe_rel(name, prefix)
            if rel is None:
                continue
            files.append(str(rel))
            if "migrations" in rel.parts and rel.suffix == ".py":
                target = settings.BASE_DIR / rel
                if not target.exists():
                    text = zf.read(name).decode("utf-8", "ignore")
                    if DESTRUCTIVE.search(text):
                        destructive.append(str(rel))
    return {
        "version": str(manifest["version"]),
        "notes": manifest.get("notes", ""),
        "delete": [d for d in manifest.get("delete", []) if isinstance(d, str)],
        "files": files,
        "destructive": destructive,
        "current": current_version(),
    }


def backup(label):
    """Full data export + code copy. Returns the two file paths."""
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    data_file = settings.BACKUP_DIR / f"{stamp}-{label}-data.json"
    with open(data_file, "w", encoding="utf-8") as fh:
        call_command(
            "dumpdata", "--natural-foreign", "--indent", "1",
            "--exclude", "contenttypes", "--exclude", "auth.permission", "--exclude", "sessions",
            stdout=fh,
        )
    code_file = settings.BACKUP_DIR / f"{stamp}-{label}-code.zip"
    with zipfile.ZipFile(code_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in _code_files():
            zf.write(path, path.relative_to(settings.BASE_DIR).as_posix())
    return data_file, code_file


def _code_files():
    base = settings.BASE_DIR
    data_dir = Path(settings.DATA_DIR).resolve()
    for root, dirs, files in os.walk(base):
        rp = Path(root)
        rel_parts = rp.relative_to(base).parts
        if rel_parts and (rel_parts[0] in PROTECTED_TOP or SKIP_PARTS & set(rel_parts)):
            dirs[:] = []
            continue
        if rp.resolve() == data_dir:
            dirs[:] = []
            continue
        for f in files:
            if not rel_parts and f in PROTECTED_TOP:
                continue
            if f.endswith((".pyc", ".log")):
                continue
            yield rp / f


def _run(args, log):
    proc = subprocess.run(
        [sys.executable, str(settings.BASE_DIR / "manage.py"), *args],
        cwd=settings.BASE_DIR, capture_output=True, text=True, timeout=900,
    )
    log.append(f"$ manage.py {' '.join(args)}\n{proc.stdout[-4000:]}{proc.stderr[-4000:]}")
    return proc.returncode == 0


def _restore_code(code_zip, log):
    with zipfile.ZipFile(code_zip) as zf:
        zf.extractall(settings.BASE_DIR)
    log.append("Previous code restored from backup.")


def reload_server(log):
    pid_file = Path(settings.GUNICORN_PID_FILE)
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGHUP)
        log.append(f"Application server reloaded (pid {pid}).")
    except (OSError, ValueError, AttributeError):
        log.append("Could not reload the application server automatically. Restart it to load the new code.")


def apply(update, zip_path, allow_destructive=False):
    """Applies a package. Returns (ok, log text)."""
    log = []
    info = inspect(zip_path)
    if info["destructive"] and not allow_destructive:
        raise UpdateError(
            "This update contains migrations that remove database tables or fields: "
            + ", ".join(info["destructive"]) + ". Confirm the checkbox to continue."
        )
    old = current_version()
    data_file, code_file = backup(f"v{old}")
    log.append(f"Backup written: {data_file.name}, {code_file.name}")

    old_reqs = (settings.BASE_DIR / "requirements.txt").read_text() if (settings.BASE_DIR / "requirements.txt").exists() else ""
    with zipfile.ZipFile(zip_path) as zf:
        prefix, _manifest = _members(zf)
        count = 0
        for name in zf.namelist():
            rel = _safe_rel(name, prefix)
            if rel is None:
                continue
            target = settings.BASE_DIR / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    log.append(f"{count} files installed.")

    for rel in info["delete"]:
        p = PurePosixPath(rel)
        if p.is_absolute() or ".." in p.parts or p.parts[0] in PROTECTED_TOP:
            continue
        target = settings.BASE_DIR / p
        if target.is_file():
            target.unlink()
            log.append(f"Removed old file {rel}")

    new_reqs = (settings.BASE_DIR / "requirements.txt").read_text() if (settings.BASE_DIR / "requirements.txt").exists() else ""
    if new_reqs != old_reqs:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(settings.BASE_DIR / "requirements.txt")],
            capture_output=True, text=True, timeout=900,
        )
        log.append("Python packages updated." if proc.returncode == 0 else f"pip failed:\n{proc.stderr[-3000:]}")
        if proc.returncode != 0:
            _restore_code(code_file, log)
            return False, "\n".join(log)

    if not _run(["migrate", "--noinput"], log):
        _restore_code(code_file, log)
        log.append("Database migration failed — the update was rolled back. Your data was not changed by this update.")
        return False, "\n".join(log)
    _run(["collectstatic", "--noinput"], log)
    _run(["demo_build"], log)  # the public demo restaurant follows the new version; never fatal

    (settings.BASE_DIR / "VERSION").write_text(info["version"] + "\n")
    log.append(f"Version {old} → {info['version']}")
    reload_server(log)
    return True, "\n".join(log)


def build_package(version, notes="", out_dir=None):
    """Creates an update ZIP of the current code (used by `manage.py make_update`)."""
    out_dir = Path(out_dir or settings.BASE_DIR / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"odg-restaurant-update-{version}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in _code_files():
            rel = path.relative_to(settings.BASE_DIR).as_posix()
            if rel == "VERSION":
                zf.writestr(rel, version + "\n")
            else:
                zf.write(path, rel)
        zf.writestr(MANIFEST, json.dumps({"version": version, "notes": notes}, indent=2))
    return target
