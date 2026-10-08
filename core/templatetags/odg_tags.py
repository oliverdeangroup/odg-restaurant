from django import template
from django.utils import dateformat, timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from core.i18n import translate
from core.models import SystemSettings

register = template.Library()


@register.simple_tag
def t(text, *args):
    """{% t "Hello {0}" name %} → translated, with {0}, {1} placeholders filled."""
    out = translate(str(text))
    if args:
        try:
            out = out.format(*args)
        except (IndexError, KeyError):
            pass
    return out


@register.filter(name="tr")
def tr_filter(text):
    return translate(str(text)) if text is not None else ""


@register.simple_tag
def icon(name, size=18, cls=""):
    return format_html(
        '<svg class="ic {}" width="{}" height="{}" aria-hidden="true"><use href="#i-{}"></use></svg>',
        cls, size, size, name,
    )


@register.filter
def fdate(value, with_time=False):
    """Formats a date with the format chosen in Settings."""
    if not value:
        return ""
    fmt = SystemSettings.load().date_format
    if hasattr(value, "tzinfo") and getattr(value, "hour", None) is not None:
        value = timezone.localtime(value) if timezone.is_aware(value) else value
        if with_time:
            fmt += " H:i"
    out = dateformat.format(value, fmt)
    if "F" in fmt:
        for en in ("January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"):
            out = out.replace(en, translate(en))
    return out


@register.filter
def fdatetime(value):
    return fdate(value, True)


@register.filter
def get(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.simple_tag(takes_context=True)
def lang_url(context, code):
    request = context["request"]
    params = request.GET.copy()
    params["lang"] = code
    return f"{request.path}?{params.urlencode()}"


@register.simple_tag(takes_context=True)
def qs(context, **kwargs):
    """Current query string with some keys replaced: {% qs page=2 %}."""
    params = context["request"].GET.copy()
    for k, v in kwargs.items():
        if v in (None, ""):
            params.pop(k, None)
        else:
            params[k] = v
    return "?" + params.urlencode() if params else "?"


@register.filter
def jsonattr(value):
    import json
    return mark_safe(json.dumps(value).replace("<", "\\u003c").replace("'", "&#39;"))


@register.simple_tag
def tjs(text, *args):
    """Translated text as a JavaScript string: {% tjs "Saved" %}."""
    import json

    out = translate(str(text))
    if args:
        try:
            out = out.format(*args)
        except (IndexError, KeyError):
            pass
    return mark_safe(json.dumps(out).replace("<", "\\u003c"))


@register.filter
def money(value):
    """12.5 → "Cg 12.50" with the currency of Settings → POS."""
    from pos.models import PosSettings

    try:
        return PosSettings.load().fmt(value or 0)
    except Exception:  # noqa: BLE001
        return value


@register.filter
def mins(seconds):
    if seconds is None:
        return "—"
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


@register.filter
def ts(value):
    """Datetime → milliseconds since 1970 (for live timers in JavaScript)."""
    if not value:
        return ""
    return int(value.timestamp() * 1000)


@register.filter
def pct(value, total):
    """Position on the floor plan as a percentage: {{ table.x|pct:settings.floor_width }}."""
    try:
        return f"{float(value) / float(total) * 100:.3f}"
    except (TypeError, ValueError, ZeroDivisionError):
        return "0"

