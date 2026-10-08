"""Cleans editor HTML so pages can't carry scripts."""
import re

import nh3

TAGS = {
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "em", "i", "u", "s", "sub", "sup",
    "blockquote", "pre", "code", "ul", "ol", "li", "a", "img", "figure", "figcaption", "span", "div",
    "table", "thead", "tbody", "tr", "th", "td", "iframe", "section", "small", "mark",
}
ATTRS = {
    "*": {"class", "style", "id"},
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height", "loading"},
    "iframe": {"src", "width", "height", "allow", "allowfullscreen", "frameborder", "loading", "title"},
    "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"},
    "ol": {"start"}, "li": {"data-list"},
}
IFRAME_OK = re.compile(r'^https://(www\.)?(youtube(-nocookie)?\.com/embed/|player\.vimeo\.com/video/|google\.com/maps/embed)')


def _filter(tag, attr, value):
    if tag == "iframe" and attr == "src" and not IFRAME_OK.match(value):
        return None
    if attr == "style" and re.search(r"expression|url\s*\(|javascript", value, re.I):
        return None
    return value


def clean_html(html):
    if not html:
        return ""
    return nh3.clean(
        html, tags=TAGS, attributes=ATTRS, attribute_filter=_filter,
        url_schemes={"http", "https", "mailto", "tel"}, link_rel="noopener",
    )
