"""ODG-RESTAURANT settings.

All machine-specific values come from the `.env` file next to manage.py
(see .env.example). Nothing in this file needs to change between the
development PC and the production server.
"""
import os
import sys
from pathlib import Path

# AlmaLinux 8 ships SQLite 3.26; Django needs 3.31+ for the demo copies.
# pysqlite3-binary brings its own modern SQLite (installed on Linux only).
try:
    import pysqlite3

    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return str(env(key, default)).lower() in ("1", "true", "yes", "on")


DEBUG = env_bool("DEBUG", False)
SECRET_KEY = env("SECRET_KEY", "dev-only-insecure-key-change-me" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is missing. Copy .env.example to .env and fill it in.")

ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
    "pos",
    "finance",
    "website",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.middleware.RequestCacheMiddleware",
    "core.demo.DemoMiddleware",  # must come before sessions: demo sessions live in the demo copy
    "django.contrib.sessions.middleware.SessionMiddleware",
    "core.middleware.LanguageMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SessionTimeoutMiddleware",
    "core.middleware.NoCacheMiddleware",
]

ROOT_URLCONF = "odg.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.odg",
            ],
            "builtins": ["core.templatetags.odg_tags"],
        },
    },
]

WSGI_APPLICATION = "odg.wsgi.application"

# ---------------------------------------------------------------- database
if env("DB_ENGINE", "sqlite") == "mysql":
    import pymysql

    # Django checks the mysqlclient version; PyMySQL is API compatible.
    pymysql.version_info = (2, 2, 1, "final", 0)
    pymysql.install_as_MySQLdb()
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("DB_NAME"),
            "USER": env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4", "init_command": "SET sql_mode='STRICT_TRANS_TABLES'"},
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

DATABASE_ROUTERS = ["core.demo.DemoRouter"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "core.User"
AUTHENTICATION_BACKENDS = ["core.auth.UsernameOrEmailBackend"]
LOGIN_URL = "core:login"
LOGIN_REDIRECT_URL = "core:dashboard"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# ---------------------------------------------------------------- i18n
LANGUAGE_CODE = "en"
USE_I18N = False  # ODG-RESTAURANT uses its own translation table (core/i18n.py)
TIME_ZONE = env("TIME_ZONE", "America/Curacao")
USE_TZ = True

# ---------------------------------------------------------------- files
# User data (uploads, backups) lives OUTSIDE the code folder so system
# updates can never overwrite or delete it.
DATA_DIR = Path(env("DATA_DIR", BASE_DIR / "data"))
MEDIA_ROOT = DATA_DIR / "media"
MEDIA_URL = "/media/"
BACKUP_DIR = DATA_DIR / "backups"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "core.storage.OdgStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000

# ---------------------------------------------------------------- security
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "SAMEORIGIN"
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    SECURE_HSTS_SECONDS = int(env("HSTS_SECONDS", "0"))  # enable once HTTPS is confirmed working

# HTTPS redirect is done by LiteSpeed (.htaccess); SAMEORIGIN framing is on purpose.
SILENCED_SYSTEM_CHECKS = ["security.W008", "security.W019", "security.W004"]

# Separate key for encrypting stored secrets (SMTP password); falls back to SECRET_KEY.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", SECRET_KEY)

# Gunicorn writes its PID here; the updater sends it SIGHUP to reload code.
GUNICORN_PID_FILE = env("GUNICORN_PID_FILE", str(BASE_DIR / "run" / "gunicorn.pid"))

EMAIL_TIMEOUT = 20

# Public address of the system, used for links in notification e-mails.
SITE_URL = env("SITE_URL", "http://127.0.0.1:8000" if DEBUG else "")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
