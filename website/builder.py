"""Drag & drop page builder (Elementor style).

A layout is JSON:
    {"sections": [
        {"id": "s1", "layout": "1-1",
         "style": {"bg": "#fff", "image": "", "overlay": 0, "padding": "md", "width": "boxed",
                   "align": "left", "dark": false, "anchor": ""},
         "columns": [{"widgets": [{"id": "w1", "type": "heading", "data": {"text": "Hi", "level": "h2"}}]},
                     {"widgets": []}]}
    ]}

`clean_layout` checks and cleans everything that comes from the browser
(widget types, lengths, URLs, HTML); `render_layout` turns it into HTML with
the templates in templates/website/widgets/.
"""
import re
import uuid

from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .sanitize import clean_html

LAYOUTS = {"1": [12], "1-1": [6, 6], "1-1-1": [4, 4, 4], "1-1-1-1": [3, 3, 3, 3], "1-2": [4, 8], "2-1": [8, 4]}
PADDINGS = ("none", "sm", "md", "lg", "xl")
WIDTHS = ("boxed", "narrow", "full")
ICONS = ("star", "clock", "pin", "phone", "mail", "calendar", "users", "glass", "chef", "leaf", "heart", "award",
         "wine", "fish", "coffee", "music", "car", "wifi", "sun", "gift")

# type → {field: kind}. Kinds: str (short text), long (multi-line text), html, url, img, int, bool, choice:a|b, list
WIDGETS = {
    "heading": {"text": "str", "level": "choice:h1|h2|h3|h4", "align": "choice:left|center|right", "sub": "str"},
    "text": {"html": "html", "align": "choice:left|center|right"},
    "image": {"src": "img", "alt": "str", "link": "url", "caption": "str", "rounded": "bool", "width": "choice:100|75|50|33"},
    "button": {"text": "str", "link": "url", "style": "choice:primary|secondary|outline", "align": "choice:left|center|right", "new_tab": "bool"},
    "hero": {"title": "str", "subtitle": "long", "button_text": "str", "button_link": "url", "button2_text": "str",
             "button2_link": "url", "image": "img", "overlay": "int", "height": "choice:md|lg|full", "align": "choice:left|center"},
    "spacer": {"height": "int"},
    "divider": {"style": "choice:line|dots|ornament"},
    "icon_box": {"icon": "choice:" + "|".join(ICONS), "title": "str", "text": "long", "align": "choice:center|left"},
    "gallery": {"images": "list:src,alt", "columns": "choice:2|3|4"},
    "video": {"url": "url", "caption": "str"},
    "map": {"query": "str", "height": "int"},
    "reviews": {"items": "list:name,rating,text,source", "title": "str", "columns": "choice:1|2|3"},
    "menu": {"categories": "ids", "show_prices": "bool", "show_images": "bool", "show_descriptions": "bool",
             "columns": "choice:1|2", "title": "str"},
    "reservation": {"title": "str", "text": "long"},
    "hours": {"title": "str"},
    "contact": {"title": "str", "show_social": "bool"},
    "social": {"align": "choice:left|center|right"},
    "html": {"code": "html"},
}

WIDGET_LABELS = {
    "heading": "Heading", "text": "Text", "image": "Image", "button": "Button", "hero": "Hero banner",
    "spacer": "Spacer", "divider": "Divider", "icon_box": "Icon box", "gallery": "Gallery", "video": "Video",
    "map": "Google Maps", "reviews": "Reviews", "menu": "Food & drinks menu", "reservation": "Online reservation",
    "hours": "Opening hours", "contact": "Contact details", "social": "Social media", "html": "HTML",
}
WIDGET_ICONS = {
    "heading": "type", "text": "note", "image": "image", "button": "send", "hero": "layers", "spacer": "spacer",
    "divider": "minus", "icon_box": "star", "gallery": "grid", "video": "play", "map": "pin", "reviews": "quote",
    "menu": "list", "reservation": "calendar", "hours": "clock", "contact": "phone", "social": "heart", "html": "code",
}

URL_OK = re.compile(r"^(https?://|/|#|mailto:|tel:)", re.I)
HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def _id(v, prefix):
    v = str(v or "")
    return v[:20] if re.fullmatch(r"[A-Za-z0-9_-]{1,20}", v) else f"{prefix}{uuid.uuid4().hex[:8]}"


def _url(v):
    v = str(v or "").strip()[:500]
    return v if not v or URL_OK.match(v) else ""


def _img(v):
    """Image URLs end up inside CSS url(...): no quotes, brackets or spaces."""
    return re.sub(r"[\s'\"()\<>]", "", _url(v))


def _clean_value(kind, v):
    if kind == "str":
        return strip_tags(str(v or ""))[:300]
    if kind == "long":
        return strip_tags(str(v or ""))[:2000]
    if kind == "html":
        return clean_html(str(v or "")[:100000])
    if kind == "url":
        return _url(v)
    if kind == "img":
        return _img(v)
    if kind == "int":
        try:
            return max(0, min(int(v), 2000))
        except (TypeError, ValueError):
            return 0
    if kind == "bool":
        return bool(v)
    if kind == "ids":
        return [int(x) for x in (v or []) if str(x).isdigit()][:50]
    if kind.startswith("choice:"):
        opts = kind[7:].split("|")
        return str(v) if str(v) in opts else opts[0]
    if kind.startswith("list:"):
        fields = kind[5:].split(",")
        out = []
        for row in (v or [])[:60]:
            if not isinstance(row, dict):
                continue
            item = {}
            for f in fields:
                if f == "src":
                    item[f] = _img(row.get(f))
                elif f == "rating":
                    try:
                        item[f] = max(1, min(int(row.get(f) or 5), 5))
                    except (TypeError, ValueError):
                        item[f] = 5
                else:
                    item[f] = strip_tags(str(row.get(f) or ""))[:1000]
            out.append(item)
        return out
    return ""


def clean_widget(w):
    if not isinstance(w, dict) or w.get("type") not in WIDGETS:
        return None
    spec = WIDGETS[w["type"]]
    data = w.get("data") if isinstance(w.get("data"), dict) else {}
    return {"id": _id(w.get("id"), "w"), "type": w["type"], "data": {k: _clean_value(kind, data.get(k)) for k, kind in spec.items()}}


def clean_layout(layout):
    if not isinstance(layout, dict):
        return {"sections": []}
    sections = []
    for sec in (layout.get("sections") or [])[:60]:
        if not isinstance(sec, dict):
            continue
        lay = sec.get("layout") if sec.get("layout") in LAYOUTS else "1"
        st = sec.get("style") if isinstance(sec.get("style"), dict) else {}
        style = {
            "bg": st.get("bg") if HEX.match(str(st.get("bg") or "")) else "",
            "image": _img(st.get("image")),
            "overlay": _clean_value("int", st.get("overlay")) if st.get("overlay") else 0,
            "padding": st.get("padding") if st.get("padding") in PADDINGS else "md",
            "width": st.get("width") if st.get("width") in WIDTHS else "boxed",
            "align": "center" if st.get("align") == "center" else "left",
            "dark": bool(st.get("dark")),
            "anchor": re.sub(r"[^a-z0-9-]", "", str(st.get("anchor") or "").lower())[:40],
        }
        style["overlay"] = min(style["overlay"], 90)
        cols_in = sec.get("columns") if isinstance(sec.get("columns"), list) else []
        cols = []
        for i in range(len(LAYOUTS[lay])):
            col = cols_in[i] if i < len(cols_in) and isinstance(cols_in[i], dict) else {}
            widgets = [cw for cw in (clean_widget(w) for w in (col.get("widgets") or [])[:40]) if cw]
            cols.append({"widgets": widgets})
        sections.append({"id": _id(sec.get("id"), "s"), "layout": lay, "style": style, "columns": cols})
    return {"sections": sections}


def layout_text(layout):
    """Plain text of a layout, for search and the SEO checks."""
    parts = []
    for sec in (layout or {}).get("sections", []):
        for col in sec.get("columns", []):
            for w in col.get("widgets", []):
                d = w.get("data", {})
                for k in ("text", "title", "subtitle", "sub", "caption"):
                    if d.get(k):
                        parts.append(str(d[k]))
                for k in ("html", "code"):
                    if d.get(k):
                        parts.append(strip_tags(d[k]))
                if w["type"] == "reviews":
                    parts += [i.get("text", "") for i in d.get("items", [])]
    return "\n".join(p for p in parts if p)


def render_layout(layout, context):
    """HTML for a layout. `context` is the website context (brand, look, …)."""
    from .widgets import widget_context

    out = []
    for sec in (layout or {}).get("sections", []):
        cols = []
        spans = LAYOUTS.get(sec.get("layout"), [12])
        for span, col in zip(spans, sec.get("columns", [])):
            html = []
            for w in col.get("widgets", []):
                ctx = dict(context)
                ctx.update(widget_context(w, context))
                ctx["w"] = w
                ctx["d"] = w.get("data", {})
                html.append(render_to_string(f"website/widgets/{w['type']}.html", ctx))
            cols.append({"span": span, "html": "".join(html)})
        out.append(render_to_string("website/widgets/_section.html", {"sec": sec, "cols": cols}))
    return "".join(out)


FIELD_LABELS = {
    "text": "Text", "level": "Size", "align": "Alignment", "sub": "Small text above", "html": "Text", "src": "Image",
    "alt": "Alt text (for Google and screen readers)", "link": "Link", "caption": "Caption", "rounded": "Rounded corners",
    "width": "Width", "style": "Style", "new_tab": "Open in a new tab", "title": "Title", "subtitle": "Subtitle",
    "button_text": "Button text", "button_link": "Button link", "button2_text": "Second button text",
    "button2_link": "Second button link", "image": "Background image", "overlay": "Darkening (0–90)", "height": "Height",
    "icon": "Icon", "images": "Images", "columns": "Columns", "url": "YouTube or Vimeo link", "query": "Address or place (empty = your address)",
    "items": "Reviews", "categories": "Categories (none = all)", "show_prices": "Show prices", "show_images": "Show photos",
    "show_descriptions": "Show descriptions", "show_social": "Show social media", "code": "HTML code",
    "name": "Name", "rating": "Stars", "source": "Source (Google, TripAdvisor …)",
}
CHOICE_LABELS = {
    "left": "Left", "center": "Centre", "right": "Right", "primary": "Filled", "secondary": "Second colour", "outline": "Outline",
    "md": "Medium", "lg": "Large", "full": "Full screen", "line": "Line", "dots": "Dots", "ornament": "Ornament",
    "100": "100%", "75": "75%", "50": "50%", "33": "33%",
}
