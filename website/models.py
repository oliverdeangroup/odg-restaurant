from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import Singleton

User = settings.AUTH_USER_MODEL

THEMES = [("bistro", "Bistro"), ("modern", "Modern"), ("lounge", "Lounge")]
THEME_DESCRIPTIONS = {
    "bistro": "Warm and classic: contact bar, logo left and menu right, serif headings, cream background.",
    "modern": "Clean and bright: full-screen hero photo with the menu over it, rounded cards.",
    "lounge": "Dark and elegant: black background, gold accents, centred logo above the menu.",
}
# Colours and fonts a theme starts with ("Apply theme colours" in Appearance).
THEME_DEFAULTS = {
    "bistro": {"primary_color": "#7a2e1d", "secondary_color": "#c8102e", "accent_color": "#d9a441",
               "background_color": "#fbf6ee", "text_color": "#2b211c", "heading_font": "Playfair Display",
               "body_font": "Lato", "header_layout": "left"},
    "modern": {"primary_color": "#0a2a7f", "secondary_color": "#c8102e", "accent_color": "#ffc800",
               "background_color": "#ffffff", "text_color": "#1f2433", "heading_font": "Poppins",
               "body_font": "Inter", "header_layout": "left"},
    "lounge": {"primary_color": "#d4af37", "secondary_color": "#8c1c13", "accent_color": "#d4af37",
               "background_color": "#111111", "text_color": "#ece6da", "heading_font": "Cormorant Garamond",
               "body_font": "Montserrat", "header_layout": "center"},
}
HEADER_LAYOUTS = [
    ("left", "Logo left, menu right"),
    ("center", "Logo centred above the menu"),
    ("split", "Menu left and right of a centred logo"),
]

FONTS = [
    "Inter", "Poppins", "Montserrat", "Lato", "Open Sans", "Roboto", "Nunito", "Merriweather",
    "Playfair Display", "Source Serif 4", "Raleway", "Work Sans", "Cormorant Garamond", "DM Serif Display",
    "Josefin Sans",
]


class Brand(Singleton):
    name = models.CharField("Restaurant name", max_length=120, default="My Restaurant")
    short_name = models.CharField(max_length=40, blank=True)
    motto = models.CharField("Slogan", max_length=200, blank=True)
    logo = models.ImageField(upload_to="public/brand/", blank=True)
    logo_light = models.ImageField(upload_to="public/brand/", blank=True, help_text="Version for dark backgrounds")
    favicon = models.ImageField(upload_to="public/brand/", blank=True)
    address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=80, blank=True, default="Willemstad")
    country = models.CharField(max_length=80, blank=True, default="Curaçao")
    phone = models.CharField(max_length=40, blank=True)
    whatsapp = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    website = models.CharField(max_length=120, blank=True)
    opening_hours = models.TextField(blank=True, default="Mon–Sun 12:00 – 22:00",
                                     help_text="Shown on the website. Booking hours are set in Settings → Reservations.")
    cuisine = models.CharField(max_length=120, blank=True, default="Caribbean, International", help_text="For Google (schema.org)")
    price_range = models.CharField(max_length=5, blank=True, default="$$")
    map_embed_url = models.URLField(max_length=500, blank=True, help_text="Google Maps → Share → Embed a map → src URL")
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    youtube = models.URLField(blank=True)
    tiktok = models.URLField(blank=True)
    tripadvisor = models.URLField(blank=True)

    def __str__(self):
        return self.name

    @property
    def socials(self):
        return [(n, u) for n, u in (
            ("facebook", self.facebook), ("instagram", self.instagram), ("youtube", self.youtube),
            ("tiktok", self.tiktok), ("tripadvisor", self.tripadvisor),
        ) if u]

    @property
    def contact_line(self):
        parts = [self.address, self.city, self.phone, self.email]
        return " · ".join(p for p in parts if p)


class Appearance(Singleton):
    theme = models.CharField(max_length=20, choices=THEMES, default="bistro")
    primary_color = models.CharField(max_length=7, default="#7a2e1d")
    secondary_color = models.CharField(max_length=7, default="#c8102e")
    accent_color = models.CharField(max_length=7, default="#d9a441")
    background_color = models.CharField(max_length=7, default="#fbf6ee")
    text_color = models.CharField(max_length=7, default="#2b211c")
    heading_font = models.CharField(max_length=40, default="Playfair Display")
    body_font = models.CharField(max_length=40, default="Lato")
    base_font_size = models.PositiveSmallIntegerField(default=16)
    radius = models.PositiveSmallIntegerField(default=10, help_text="Corner roundness in px")
    # Hero banner
    hero_enabled = models.BooleanField(default=True)
    hero_image = models.ImageField(upload_to="public/hero/", blank=True)
    hero_title = models.CharField(max_length=160, blank=True, default="Fresh food, island flavours")
    hero_subtitle = models.CharField(max_length=300, blank=True, default="Lunch and dinner with a view. Book your table online.")
    hero_button_text = models.CharField(max_length=60, blank=True, default="Book a table")
    hero_button_link = models.CharField(max_length=255, blank=True, default="/reservations/")
    hero_overlay = models.PositiveSmallIntegerField(default=45, help_text="Darkening over the image, 0–90 %")
    # Header
    header_layout = models.CharField(max_length=10, choices=HEADER_LAYOUTS, default="left")
    header_sticky = models.BooleanField(default=True)
    header_topbar = models.BooleanField(default=True, help_text="Small bar with phone, e-mail and opening hours")
    header_cta_text = models.CharField(max_length=40, blank=True, default="Book a table")
    header_cta_link = models.CharField(max_length=255, blank=True, default="/reservations/")
    # Footer: built with the same drag & drop builder as the pages
    footer_layout = models.JSONField(default=dict, blank=True)
    footer_text = models.TextField(blank=True)
    footer_show_social = models.BooleanField(default=True)
    footer_show_powered = models.BooleanField(default=True)
    custom_css = models.TextField(blank=True)

    def __str__(self):
        return "Appearance"


class Page(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    class Template(models.TextChoices):
        DEFAULT = "default", "Default"
        FULL = "full", "Full width"
        LANDING = "landing", "Landing (with hero)"
        CANVAS = "canvas", "Canvas (no page title)"

    class Editor(models.TextChoices):
        BUILDER = "builder", "Drag & drop builder"
        HTML = "html", "HTML editor"

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    editor = models.CharField(max_length=10, choices=Editor.choices, default=Editor.BUILDER)
    layout = models.JSONField(default=dict, blank=True, help_text="Sections, columns and widgets of the builder")
    content = models.TextField(blank=True, help_text="HTML of the HTML editor")
    excerpt = models.TextField(blank=True)
    featured_image = models.ImageField(upload_to="public/pages/", blank=True)
    template = models.CharField(max_length=10, choices=Template.choices, default=Template.DEFAULT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    is_homepage = models.BooleanField(default=False)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    order = models.PositiveSmallIntegerField(default=0)
    # SEO
    meta_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=170, blank=True)
    focus_keyword = models.CharField(max_length=80, blank=True, help_text="The search term this page should be found with")
    og_image = models.ImageField(upload_to="public/pages/", blank=True)
    noindex = models.BooleanField(default=False)
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return "/" if self.is_homepage else reverse("website:page", args=[self.slug])

    def save(self, *args, **kwargs):
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)
        if self.is_homepage:
            Page.objects.exclude(pk=self.pk).filter(is_homepage=True).update(is_homepage=False)


class PageRevision(models.Model):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="revisions")
    title = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    layout = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


class MediaFile(models.Model):
    file = models.FileField(upload_to="public/library/%Y/%m/")
    title = models.CharField(max_length=200, blank=True)
    alt = models.CharField("Alt text", max_length=200, blank=True)
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_image(self):
        return self.file.name.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "gif", "webp", "svg")


class Menu(models.Model):
    class Location(models.TextChoices):
        HEADER = "header", "Header (main menu)"
        FOOTER = "footer", "Footer"
        NONE = "none", "Not shown (use in a widget)"

    name = models.CharField(max_length=80)
    location = models.CharField(max_length=10, choices=Location.choices, default=Location.NONE)

    def __str__(self):
        return self.name

    def tree(self):
        items = list(self.items.select_related("page").all())
        top = [i for i in items if i.parent_id is None]
        for i in top:
            i.subs = [c for c in items if c.parent_id == i.id]
        return top


class MenuItem(models.Model):
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name="items")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    label = models.CharField(max_length=80)
    page = models.ForeignKey(Page, null=True, blank=True, on_delete=models.SET_NULL)
    url = models.CharField(max_length=255, blank=True, help_text="Used when no page is chosen")
    new_tab = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.label

    @property
    def href(self):
        if self.page_id:
            return self.page.get_absolute_url()
        return self.url or "#"


class SEOSettings(Singleton):
    site_title = models.CharField(max_length=70, blank=True, help_text="Defaults to the restaurant name")
    title_separator = models.CharField(max_length=5, default="|")
    meta_description = models.CharField(max_length=170, blank=True)
    meta_keywords = models.CharField(max_length=255, blank=True)
    default_og_image = models.ImageField(upload_to="public/seo/", blank=True)
    allow_indexing = models.BooleanField(default=True, help_text="Let Google and Bing index the website")
    sitemap_enabled = models.BooleanField(default=True)
    robots_extra = models.TextField(blank=True, help_text="Extra lines for robots.txt")
    canonical_domain = models.CharField(max_length=120, blank=True, help_text="e.g. https://www.myrestaurant.cw")
    google_verification = models.CharField(max_length=120, blank=True)
    bing_verification = models.CharField(max_length=120, blank=True)
    google_analytics_id = models.CharField(max_length=30, blank=True, help_text="GA4 ID, e.g. G-XXXXXXX")
    schema_type = models.CharField(
        max_length=30, default="Restaurant",
        choices=[("Restaurant", "Restaurant"), ("BarOrPub", "Bar or pub"), ("CafeOrCoffeeShop", "Café / coffee shop"),
                 ("FastFoodRestaurant", "Fast food"), ("Bakery", "Bakery"), ("Winery", "Wine bar"),
                 ("Organization", "Company (not a restaurant)")],
    )
    breadcrumbs = models.BooleanField("Breadcrumbs (schema.org)", default=True)
    redirects = models.TextField(blank=True, help_text="One per line: /old-address/ /new-address/ (permanent 301 redirect)")

    def __str__(self):
        return "SEO"

    def redirect_map(self):
        out = {}
        for line in self.redirects.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0].startswith("/"):
                out[parts[0].rstrip("/") or "/"] = parts[1]
        return out
