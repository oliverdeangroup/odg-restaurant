from contextvars import ContextVar

from django.contrib.auth.models import AbstractUser
from django.db import models, router
from django.utils import timezone

from .fields import EncryptedTextField


class Role(models.TextChoices):
    ADMIN = "admin", "Administrator"
    MODERATOR = "moderator", "Moderator"
    OWNER = "owner", "Owner"
    MANAGER = "manager", "Manager"
    WAITER = "waiter", "Waiter"
    BARTENDER = "bartender", "Bartender"
    CHEF = "chef", "Chef"


SYSTEM_ROLES = (Role.ADMIN, Role.MODERATOR)
STAFF_ROLES = (Role.OWNER, Role.MANAGER, Role.WAITER, Role.BARTENDER, Role.CHEF)

LANGUAGE_CHOICES = [("en", "English"), ("nl", "Nederlands"), ("es", "Español")]


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.WAITER)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    birthdate = models.DateField(null=True, blank=True)
    id_number = models.CharField("ID number", max_length=60, blank=True)
    photo = models.ImageField(upload_to="private/avatars/", blank=True)
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, blank=True)
    bio = models.TextField(blank=True)

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_system(self):
        return self.is_superuser or self.role in SYSTEM_ROLES

    @property
    def is_admin(self):
        return self.is_superuser or self.role == Role.ADMIN

    @property
    def photo_url(self):
        """Profile photos are private: served only to logged-in users."""
        if not self.photo:
            return ""
        import zlib

        from django.urls import reverse

        return f"{reverse('core:avatar', args=[self.pk])}?v={zlib.crc32(self.photo.name.encode()) % 100000}"

    @property
    def initials(self):
        parts = [p for p in (self.first_name, self.last_name) if p]
        return "".join(p[0] for p in parts).upper() or self.username[:2].upper()


# Settings rows are read many times per page; they are cached for one request
# (core.middleware.RequestCacheMiddleware empties the cache at the start).
_singletons = ContextVar("odg_singletons", default=None)


def start_singleton_cache():
    return _singletons.set({})


def end_singleton_cache(token):
    _singletons.reset(token)


class Singleton(models.Model):
    """A settings table that always has exactly one row."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache = _singletons.get()
        if cache is not None:
            cache[(type(self), router.db_for_write(type(self)))] = self

    @classmethod
    def load(cls):
        cache = _singletons.get()
        key = (cls, router.db_for_read(cls))
        if cache is not None and key in cache:
            return cache[key]
        obj, _ = cls.objects.get_or_create(pk=1)
        if cache is not None:
            cache[key] = obj
        return obj


class SystemSettings(Singleton):
    system_name = models.CharField(max_length=80, default="ODG-RESTAURANT")
    default_language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default="en")
    date_format = models.CharField(
        max_length=20,
        default="d-m-Y",
        choices=[("d-m-Y", "31-12-2026"), ("d/m/Y", "31/12/2026"), ("Y-m-d", "2026-12-31"), ("j F Y", "31 December 2026")],
    )
    # Role limits
    max_managers = models.PositiveSmallIntegerField(default=2)
    # Security
    password_min_length = models.PositiveSmallIntegerField(default=8)
    session_timeout_minutes = models.PositiveIntegerField(default=120)
    max_login_attempts = models.PositiveSmallIntegerField(default=5)
    lockout_minutes = models.PositiveSmallIntegerField(default=15)
    # Outgoing e-mail used for notifications and password mails
    smtp_enabled = models.BooleanField(default=False)
    smtp_host = models.CharField(max_length=120, blank=True)
    smtp_port = models.PositiveIntegerField(default=465)
    smtp_security = models.CharField(max_length=10, default="ssl", choices=[("ssl", "SSL/TLS"), ("starttls", "STARTTLS"), ("none", "None")])
    smtp_username = models.CharField(max_length=120, blank=True)
    smtp_password = EncryptedTextField(blank=True)
    smtp_from_email = models.EmailField(blank=True)
    smtp_from_name = models.CharField(max_length=80, blank=True)
    # Notifications
    notify_by_email = models.BooleanField(default=True)
    # Website
    demo_enabled = models.BooleanField(
        "Public demo", default=True,
        help_text="Allow visitors to try the Waiter, Bartender, Chef, Manager and Owner dashboards at /demo/ without logging in.",
    )
    maintenance_mode = models.BooleanField(default=False)
    maintenance_message = models.TextField(blank=True, default="We are working on our website. Please come back soon.")
    # Activity log retention (orders and finance are kept by law, see pos/finance)
    activity_log_days = models.PositiveIntegerField(default=365)

    def __str__(self):
        return "System settings"


class ActivityLog(models.Model):
    class Kind(models.TextChoices):
        LOGIN = "login", "Login"
        CREATE = "create", "Created"
        UPDATE = "update", "Updated"
        DELETE = "delete", "Deleted"
        UPLOAD = "upload", "Upload"
        DOWNLOAD = "download", "Download"
        SYSTEM = "system", "System"

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="activity")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    area = models.CharField(max_length=40, blank=True)
    message = models.CharField(max_length=255)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.message


class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=160)
    message = models.CharField(max_length=255, blank=True)
    link = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=30, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class SystemUpdate(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        APPLIED = "applied", "Applied"
        FAILED = "failed", "Failed"
        ROLLED_BACK = "rolled_back", "Rolled back"

    version = models.CharField(max_length=30)
    previous_version = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    log = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


class DemoSandbox(models.Model):
    """One visitor's private demo copy (the data itself lives in DATA_DIR/demo/sandboxes/<code>)."""

    code = models.CharField(max_length=12, unique=True)
    role = models.CharField(max_length=10, help_text="Role the visitor started with")
    ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    stamp = models.CharField(max_length=20)
    created_at = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-last_seen"]

    def __str__(self):
        return self.code

    @property
    def is_expired(self):
        from datetime import timedelta

        from .demo import HOURS_IDLE, HOURS_MAX

        now = timezone.now()
        return self.last_seen < now - timedelta(hours=HOURS_IDLE) or self.created_at < now - timedelta(hours=HOURS_MAX)

    @property
    def expires_at(self):
        from datetime import timedelta

        from .demo import HOURS_IDLE, HOURS_MAX

        return min(self.last_seen + timedelta(hours=HOURS_IDLE), self.created_at + timedelta(hours=HOURS_MAX))
