"""Lists interface texts that have no Dutch/Spanish translation yet.

    python manage.py i18n_strings            # missing ones
    python manage.py i18n_strings --all      # every text found
"""
import re
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models

from core.translations import STRINGS

TEMPLATE_RE = re.compile(r"""\{%\s*t(?:js)?\s+"((?:[^"\\]|\\.)*)"|\{%\s*t(?:js)?\s+'((?:[^'\\]|\\.)*)'""")
PY_RE = re.compile(r"""\b_\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')\s*[,)]""")
NOTIFY_RE = re.compile(r"""notify\([^,]+,\s*(?:NOTIFY_TEXT\[[^\]]+\]|"((?:[^"\\]|\\.)*)")""")


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true")

    def handle(self, *args, **o):
        found = set()
        base = Path(settings.BASE_DIR)
        for f in (base / "templates").rglob("*.html"):
            for m in TEMPLATE_RE.finditer(f.read_text(encoding="utf-8")):
                found.add(m.group(1) or m.group(2))
        for f in list(base.glob("*/*.py")) + list(base.glob("*/management/commands/*.py")):
            if ".venv" in f.parts:
                continue
            text = f.read_text(encoding="utf-8")
            found.update(m.group(1) or m.group(2) for m in PY_RE.finditer(text))
            found.update(m.group(1) for m in NOTIFY_RE.finditer(text) if m.group(1))
        from core.nav import MENU
        from website.builder import WIDGET_LABELS
        from website.models import THEME_DESCRIPTIONS, THEMES

        from website.builder import CHOICE_LABELS, FIELD_LABELS
        from website.widgets import WEEKDAYS

        found.update(WIDGET_LABELS.values())
        found.update(FIELD_LABELS.values())
        found.update(CHOICE_LABELS.values())
        found.update(WEEKDAYS)
        found.update(n for _k, n in THEMES)
        found.update(THEME_DESCRIPTIONS.values())
        for label, _i, subs in MENU:
            found.add(label)
            found.update(s[0] for s in subs)
        for model in apps.get_models():
            if model._meta.app_label not in ("core", "pos", "finance", "website"):
                continue
            for field in model._meta.get_fields():
                if not isinstance(field, models.Field):
                    continue
                if field.verbose_name:
                    found.add(str(field.verbose_name)[0].upper() + str(field.verbose_name)[1:])
                if field.help_text:
                    found.add(str(field.help_text))
                for _v, label in field.choices or []:
                    found.add(str(label))
        from core import forms as cf
        from finance import views as fv
        from pos import forms as pf
        from website import forms as wf

        for mod in (cf, pf, wf, fv):
            for obj in vars(mod).values():
                if isinstance(obj, type) and issubclass(obj, (cf.forms.Form, cf.forms.ModelForm)) and obj not in (cf.forms.Form, cf.forms.ModelForm):
                    for fld in obj.base_fields.values():
                        if fld.label:
                            found.add(str(fld.label))
                        if fld.help_text:
                            found.add(str(fld.help_text))
                        for _v, label in getattr(fld, "choices", None) or []:
                            if isinstance(label, str):
                                found.add(label)
        found = {s for s in found if s and any(c.isalpha() for c in s)}
        rows = sorted(found if o["all"] else (s for s in found if s not in STRINGS), key=str.lower)
        for s in rows:
            self.stdout.write(s)
        self.stderr.write(f"{len(rows)} strings")
