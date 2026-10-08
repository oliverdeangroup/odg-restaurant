import logging
import secrets
import string
import threading

from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend

from .models import ActivityLog, Notification, SystemSettings

log = logging.getLogger(__name__)


def client_ip(request):
    if request is None:
        return None
    # Behind NGINX → LiteSpeed → Gunicorn the socket address is always 127.0.0.1;
    # NGINX passes the visitor's address in X-Real-IP / X-Forwarded-For.
    import ipaddress

    candidates = [request.META.get("HTTP_X_REAL_IP", "")]
    candidates += [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")]
    candidates.append(request.META.get("REMOTE_ADDR", ""))
    for c in candidates:
        try:
            ip = ipaddress.ip_address(c)
        except ValueError:
            continue
        if not (ip.is_loopback or ip.is_private) or c == candidates[-1]:
            return c
    return None


def log_activity(request, kind, message, area="", user=None):
    if user is None and request is not None and request.user.is_authenticated:
        user = request.user
    ActivityLog.objects.create(user=user, kind=kind, area=area, message=message[:255], ip=client_ip(request))


def system_mail_backend():
    s = SystemSettings.load()
    if not s.smtp_enabled or not s.smtp_host:
        return None
    return EmailBackend(
        host=s.smtp_host,
        port=s.smtp_port,
        username=s.smtp_username or None,
        password=s.smtp_password or None,
        use_ssl=s.smtp_security == "ssl",
        use_tls=s.smtp_security == "starttls",
        timeout=20,
    )


def send_system_mail(to, subject, body, background=True):
    """Sends a mail with the SMTP account from Settings. Silently skips if not set up."""
    s = SystemSettings.load()
    backend = system_mail_backend()
    to = [a for a in to if a]
    if backend is None or not to:
        return False
    sender = f"{s.smtp_from_name} <{s.smtp_from_email}>" if s.smtp_from_name else s.smtp_from_email
    msg = EmailMessage(subject, body, sender or None, bcc=to, connection=backend)

    def _send():
        try:
            msg.send()
        except Exception:  # noqa: BLE001 - never break a page because mail failed
            log.exception("Notification e-mail failed")

    if background:
        threading.Thread(target=_send, daemon=True).start()
    else:
        _send()
    return True


def notify(users, title, message="", link="", category="", args=(), email=True):
    """Creates an in-app notification (and e-mail) for each user.

    `title` is English text with {0} placeholders; it is translated into
    each recipient's own language before it is stored and mailed.
    """
    from django.conf import settings

    from .i18n import translate

    default_lang = SystemSettings.load().default_language
    seen, rows, mails = set(), [], {}
    for u in users:
        if u is None or not u.is_active or u.pk in seen:
            continue
        seen.add(u.pk)
        lang = u.language or default_lang
        text = translate(title, lang).format(*args)
        rows.append(Notification(recipient=u, title=text[:160], message=message[:255], link=link, category=category))
        if u.email:
            mails.setdefault(text, []).append(u.email)
    Notification.objects.bulk_create(rows)
    if email and SystemSettings.load().notify_by_email:
        url = (settings.SITE_URL.rstrip("/") + link) if link.startswith("/") and settings.SITE_URL else link
        for text, addresses in mails.items():
            send_system_mail(addresses, text, f"{message}\n\n{url}".strip())


def random_password(length=12):
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isdigit() for c in pw) and any(c.isupper() for c in pw) and any(c.islower() for c in pw):
            return pw
