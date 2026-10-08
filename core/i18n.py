"""ODG-RESTAURANT translations: English (source), Dutch and Spanish.

Use `_("English text")` in Python and `{% t "English text" %}` in templates.
Strings are looked up in core/translations.py; anything missing falls back
to English, so a missing translation never breaks a page.
"""
from contextvars import ContextVar

from .translations import STRINGS

LANGUAGES = [("en", "English"), ("nl", "Nederlands"), ("es", "Español")]
LANG_CODES = {code for code, _ in LANGUAGES}
_INDEX = {"nl": 0, "es": 1}
_current = ContextVar("odg_lang", default="en")


def set_language(code):
    _current.set(code if code in LANG_CODES else "en")


def get_language():
    return _current.get()


def translate(text, lang=None):
    lang = lang or _current.get()
    if lang not in _INDEX or not text:
        return text
    entry = STRINGS.get(str.__str__(text) if isinstance(text, str) else text)
    if not entry:
        return text
    return entry[_INDEX[lang]] or text


_ = translate
