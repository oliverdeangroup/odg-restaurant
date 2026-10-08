from django import forms
from django.utils.text import slugify

from core.forms import StyledMixin
from core.i18n import _

from .models import FONTS, Appearance, Brand, MediaFile, Menu, MenuItem, Page, SEOSettings
from .sanitize import clean_html

RESERVED_SLUGS = {"dashboard", "login", "logout", "media", "static", "sitemap.xml", "robots.txt", "demo", "book"}


class PageForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Page
        fields = [
            "title", "slug", "editor", "content", "excerpt", "featured_image", "template", "status", "is_homepage",
            "parent", "order", "meta_title", "meta_description", "focus_keyword", "og_image", "noindex",
        ]
        widgets = {"content": forms.HiddenInput(), "excerpt": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = _("Part of the web address. Leave empty to make it from the title.")
        qs = Page.objects.all()
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = qs
        self.fields["meta_title"].widget.attrs["maxlength"] = 70
        self.fields["meta_description"].widget.attrs["maxlength"] = 170

    def clean_slug(self):
        slug = slugify(self.cleaned_data.get("slug") or self.cleaned_data.get("title") or "") or "page"
        if slug in RESERVED_SLUGS:
            slug = f"{slug}-page"
        base, n = slug, 2
        while Page.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    def clean_content(self):
        return clean_html(self.cleaned_data.get("content", ""))


FONT_CHOICES = [(f, f) for f in FONTS]


class AppearanceForm(StyledMixin, forms.ModelForm):
    heading_font = forms.ChoiceField(choices=FONT_CHOICES)
    body_font = forms.ChoiceField(choices=FONT_CHOICES)

    class Meta:
        model = Appearance
        exclude = ["id", "footer_layout"]
        widgets = {
            "theme": forms.RadioSelect,
            **{f: forms.TextInput(attrs={"type": "color"}) for f in (
                "primary_color", "secondary_color", "accent_color", "background_color", "text_color")},
            "hero_overlay": forms.NumberInput(attrs={"type": "range", "min": 0, "max": 90}),
            "custom_css": forms.Textarea(attrs={"rows": 5, "spellcheck": "false", "style": "font-family:monospace"}),
            "footer_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["theme"].widget.attrs["class"] = ""

    def clean_custom_css(self):
        css = self.cleaned_data.get("custom_css", "")
        return css.replace("</style", "")


class BrandForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Brand
        exclude = ["id"]
        widgets = {"opening_hours": forms.Textarea(attrs={"rows": 3})}


class SEOForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = SEOSettings
        exclude = ["id"]
        widgets = {"robots_extra": forms.Textarea(attrs={"rows": 3, "style": "font-family:monospace"}),
                   "redirects": forms.Textarea(attrs={"rows": 3, "style": "font-family:monospace", "placeholder": "/old-menu/ /menu/"})}


class MenuForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Menu
        fields = ["name", "location"]


class MenuItemForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ["label", "page", "url", "parent", "order", "new_tab"]

    def __init__(self, *args, menu=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["page"].queryset = Page.objects.filter(status=Page.Status.PUBLISHED)
        self.fields["parent"].queryset = MenuItem.objects.filter(menu=menu, parent=None) if menu else MenuItem.objects.none()
        self.fields["parent"].help_text = _("Choose a parent to make this a submenu item.")
        self.fields["label"].required = False

    def clean(self):
        d = super().clean()
        if not d.get("label") and d.get("page"):
            d["label"] = d["page"].title
        if not d.get("label"):
            self.add_error("label", _("Give the menu item a name."))
        return d


class MediaForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = MediaFile
        fields = ["file", "title", "alt"]

    def clean_file(self):
        f = self.cleaned_data["file"]
        ext = f.name.lower().rsplit(".", 1)[-1]
        allowed = {"jpg", "jpeg", "png", "gif", "webp", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "mp4", "mp3"}
        if ext not in allowed:
            raise forms.ValidationError(_("This file type is not allowed."))
        return f
