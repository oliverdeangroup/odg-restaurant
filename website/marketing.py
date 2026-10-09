"""The product website of ODG-RESTAURANT itself (restaurant.oliverdeangroup.com).

`python manage.py marketing_site` puts these pages in place. It only replaces
the untouched starter pages; pages you made yourself are kept.
"""
from django.core.files import File
from django.conf import settings

from .builder import clean_layout
from .models import Appearance, Brand, Menu, MenuItem, Page, SEOSettings
from .starter import sec, w

S = "/static/odg/img/screens/"
VIDEO = "/static/odg/video/demo-tour.webm"
NAVY, DARK = "#0a2a7f", "#071237"


def img(name, alt):
    return w("image", src=f"{S}{name}.jpg", alt=alt, link="", caption="", rounded=True, width="100")


def feature(title, kicker, html, shot, alt, image_left=False, bg=""):
    text = [w("heading", text=title, level="h2", align="left", sub=kicker), w("text", html=html, align="left")]
    pic = [img(shot, alt)]
    cols = (pic, text) if image_left else (text, pic)
    return sec("1-1", *cols, padding="lg", bg=bg)


def home():
    return {"sections": [
        sec("1", [w("hero", title="Run your whole restaurant from one screen",
                    subtitle="ODG-RESTAURANT is the restaurant system for Curaçao: a live POS for waiters, bar and kitchen, "
                             "a Cassa with PDF bills, reservations, finance and your own website — in English, Dutch and Spanish.",
                    button_text="Try the live demo", button_link="/demo/", button2_text="Watch the 1-minute tour", button2_link="#tour",
                    image="", overlay=0, height="lg", align="center")], padding="none", width="full"),
        sec("1-1",
            [w("heading", text="Everything connected, in real time", level="h2", align="left", sub="One system"),
             w("text", html="<p>The waiter takes the order per guest on a tablet. Drinks go straight to the bar, food to the kitchen. "
                            "When a dish is ready the waiter gets a signal, serves it, and the manager closes the table in the Cassa.</p>"
                            "<p>Every screen updates by itself within seconds — no refresh, no paper tickets, no shouting through the kitchen door.</p>",
                    align="left"),
             w("button", text="See all features", link="/features/", style="primary", align="left", new_tab=False)],
            [img("waiter-floor", "Live floor plan with the status of every table")], padding="lg"),
        sec("1-1-1",
            [w("icon_box", icon="pos", title="POS per table and guest", text="Guest #1, Guest #2 … with options like doneness, side and notes.", align="center")],
            [w("icon_box", icon="chef", title="Bar & kitchen screens", text="Live queues with timers. Late tickets turn red automatically.", align="center")],
            [w("icon_box", icon="cash", title="Cassa", text="Split bills, tips, cash or card, and PDF bills in 80 mm, A5 or A4.", align="center")],
            padding="md", bg="#f3f6fc"),
        sec("1-1-1",
            [w("icon_box", icon="grid", title="Floor & reservations", text="Design your floor and take bookings online in 30-minute slots.", align="center")],
            [w("icon_box", icon="chart", title="Finance & OB", text="Profit & Loss, OB summary and PDF reports with your logo.", align="center")],
            [w("icon_box", icon="globe", title="Your own website", text="Drag & drop builder with your live menu and online booking.", align="center")],
            padding="md", bg="#f3f6fc"),
        sec("1", [w("heading", text="See it in action", level="h2", align="center", sub="1-minute tour"),
                  w("video", url=VIDEO, poster=f"{S}video-poster.jpg", caption="From the guest's booking to the kitchen, the Cassa and the finance report.")],
            padding="lg", width="narrow", anchor="tour"),
        feature("Kitchen and bar displays", "For chefs and bartenders",
                "<p>Every food order appears on the kitchen screen and every drink at the bar — oldest first, with the table, the guest "
                "numbers, the preparation details and a running timer.</p><ul><li>Doneness, pasta type, sides and notes in clear labels</li>"
                "<li>Tickets turn yellow when due and red when late</li><li>One tap on ✓ and the waiter is told to pick it up</li></ul>",
                "kitchen", "Kitchen display with live tickets", image_left=True, bg="#f3f6fc"),
        feature("A Cassa that does the maths", "For managers and owners",
                "<p>Pay the whole table or split the bill per guest. Add a tip with one click, take cash with the change calculated, "
                "or card. Pro-forma bills and receipts are saved as PDF, numbered without gaps.</p><ul><li>OB (sales tax) on every bill</li>"
                "<li>CRIB and KvK number printed automatically</li><li>Day close with cash count (Z report)</li></ul>",
                "cassa", "Cassa with split bill per guest"),
        feature("Finance made for Curaçao", "Profit & Loss",
                "<p>See your sales, OB, tips, expenses and result per day, week, month or year. Download the PDF report with your logo "
                "for your accountant, or export the bill register to Excel.</p><ul><li>XCG (Caribbean guilder) and OB 6 % by default</li>"
                "<li>OB collected minus OB paid on expenses</li><li>Records are kept for the 10-year rule</li></ul>",
                "finance", "Finance overview with profit and loss", image_left=True, bg="#f3f6fc"),
        feature("Your restaurant website, included", "Website builder",
                "<p>Build your website with drag & drop: hero banners, your live food & drinks menu, reviews, Google Maps, "
                "opening hours and online booking. Three themes, SEO tools like Rank Math, and everything in three languages.</p>"
                "<p>Bookings from the website appear in the dashboard at once — see it on our demo restaurant, Dinosaur BBQ.</p>",
                "site-home", "Example restaurant website made with ODG-RESTAURANT"),
        sec("1-1-1-1",
            [w("icon_box", icon="cash", title="XCG & OB", text="Caribbean guilder and Curaçao sales tax built in.", align="center")],
            [w("icon_box", icon="receipt", title="Legal bills", text="Gapless numbers, CRIB and KvK on every bill.", align="center")],
            [w("icon_box", icon="shield", title="Your data stays", text="Updates never delete orders, bills or customers.", align="center")],
            [w("icon_box", icon="globe", title="EN · NL · ES", text="Every screen in English, Dutch and Spanish.", align="center")],
            padding="lg"),
        sec("1", [w("heading", text="Try it now — no login needed", level="h2", align="center", sub="Live demo"),
                  w("text", html="<p style=\"text-align:center\">Step into our demo restaurant as waiter, bartender, chef, manager or owner, "
                                 "or book a table on its website and watch the reservation arrive.</p>", align="center"),
                  w("button", text="Open the live demo", link="/demo/", style="primary", align="center", new_tab=False),
                  w("button", text="Visit the demo restaurant website", link="/demo/site/", style="outline", align="center", new_tab=False)],
            padding="xl", dark=True, bg=DARK, align="center"),
        sec("1", [w("heading", text="Want ODG-RESTAURANT for your restaurant?", level="h2", align="center", sub="Oliver Dean Group"),
                  w("text", html="<p style=\"text-align:center\">We install it on your own domain, set up your menu, floor and staff, and train your team.</p>",
                    align="center"),
                  w("button", text="Contact us", link="/contact/", style="primary", align="center", new_tab=False)],
            padding="lg", align="center"),
    ]}


def features():
    return {"sections": [
        sec("1", [w("hero", title="Features", subtitle="One system for the whole team — each role sees exactly what it needs.",
                    button_text="Try the live demo", button_link="/demo/", button2_text="", button2_link="", image="", overlay=0,
                    height="md", align="center")], padding="none", width="full"),
        feature("Waiter", "Take orders",
                "<ul><li>Live floor with the status of every table</li><li>Order per guest: Guest #1, Guest #2 …</li>"
                "<li>Options like doneness and side, plus notes</li><li>Signal with sound when food or drinks are ready</li>"
                "<li>Mark items as served, request the bill, move a table</li></ul>", "waiter-options", "Ordering with options per guest"),
        feature("Chef & bartender", "Live queues",
                "<ul><li>Food goes to the kitchen, drinks to the bar — automatically</li><li>Table, guest, items, details, time and estimate</li>"
                "<li>Mark items as completed, or undo</li><li>Average preparation time of today</li></ul>", "bar", "Bar queue", image_left=True, bg="#f3f6fc"),
        feature("Manager", "Run the floor",
                "<ul><li>Live overview of every open table</li><li>Cassa: split bill, tip, cash or card, PDF bills</li>"
                "<li>Reservations by day, week or month</li><li>Staff performance: tables, sales, preparation and pick-up times</li></ul>",
                "overview", "Live overview for the manager"),
        feature("Floor manager", "Design your room",
                "<ul><li>Rectangle and round tables, any size</li><li>Sections like Terrace and Dining room</li>"
                "<li>Colour-coded live floor for everybody</li><li>Mini reservation timeline per table</li></ul>",
                "floor-design", "Floor designer", image_left=True, bg="#f3f6fc"),
        feature("Reservations & customers", "Never lose a booking",
                "<ul><li>Online booking in 30-minute slots, only free tables</li><li>A table stays unavailable until it is paid</li>"
                "<li>Customer profiles: ID, contact, reservation history, past orders, table history</li></ul>",
                "reservations", "Reservations per week"),
        feature("Owner", "The full picture",
                "<ul><li>Profit & Loss per day, week, month and year</li><li>OB summary for the monthly return</li>"
                "<li>PDF reports with your logo, CSV export for the accountant</li><li>Live POS, reservations and the day's sales on the home screen</li></ul>",
                "owner-home", "Home screen for the owner", image_left=True, bg="#f3f6fc"),
        feature("Website", "Online, your way",
                "<ul><li>Drag & drop builder with sections and widgets, plus an HTML editor</li><li>Header and footer builders, 3 themes</li>"
                "<li>Your live menu from the POS and online booking</li><li>SEO score per page, sitemap and schema.org</li></ul>",
                "site-menu", "Restaurant menu page on the website"),
        sec("1-1-1",
            [w("icon_box", icon="users", title="Roles", text="Administrator, moderator, owner, manager, waiter, bartender and chef.", align="center")],
            [w("icon_box", icon="refresh", title="Safe updates", text="Upload an update: a backup is made first and your data is never touched.", align="center")],
            [w("icon_box", icon="globe", title="Three languages", text="English, Dutch and Spanish — every user picks their own.", align="center")],
            padding="lg"),
        sec("1", [w("heading", text="See for yourself", level="h2", align="center", sub=""),
                  w("button", text="Open the live demo", link="/demo/", style="primary", align="center", new_tab=False)],
            padding="lg", dark=True, bg=DARK, align="center"),
    ]}


def contact():
    return {"sections": [
        sec("1-1", [w("heading", text="Contact", level="h1", align="left", sub="Oliver Dean Group"),
                    w("text", html="<p>Would you like ODG-RESTAURANT for your restaurant, bar or café? We install it on your own domain, "
                                   "set up your menu, floor plan and staff accounts, and train your team.</p>", align="left"),
                    w("contact", title="", show_social=True)],
            [img("cassa", "ODG-RESTAURANT Cassa")], padding="lg"),
    ]}


def footer():
    return {"sections": [
        sec("1-1-1",
            [w("heading", text="ODG-RESTAURANT", level="h3", align="left", sub=""),
             w("text", html="<p>The restaurant system for Curaçao, by Oliver Dean Group.</p>", align="left"), w("social", align="left")],
            [w("heading", text="Explore", level="h4", align="left", sub=""),
             w("text", html="<p><a href=\"/features/\">Features</a><br><a href=\"/demo/\">Live demo</a><br>"
                            "<a href=\"/demo/site/\">Demo restaurant website</a><br><a href=\"/login/\">Log in</a></p>", align="left")],
            [w("heading", text="Contact", level="h4", align="left", sub=""),
             w("text", html="<p>Want ODG-RESTAURANT for your restaurant? We are happy to show you around.</p>", align="left"),
             w("button", text="Contact us", link="/contact/", style="outline", align="left", new_tab=False)],
            padding="lg", dark=True, bg=DARK),
    ]}


def create(replace_starter=True):
    """Builds the product website. Returns the pages that were created."""
    from . import starter

    starter_slugs = {"home", "menu", "reservations", "about-us", "contact"}
    if replace_starter:
        # Only the untouched starter pages are replaced.
        for p in Page.objects.filter(slug__in=starter_slugs):
            if not p.revisions.exists():
                p.delete()
        Menu.objects.filter(name="Main menu").delete()
    made = []
    for i, (title, slug, layout, is_home, tpl, kw, desc) in enumerate([
        ("Home", "home", home(), True, "canvas", "restaurant system Curaçao",
         "ODG-RESTAURANT: the restaurant system for Curaçao. Live POS, bar & kitchen screens, Cassa, reservations, finance and your own website."),
        ("Features", "features", features(), False, "canvas", "restaurant POS features",
         "All features of ODG-RESTAURANT: POS per guest, kitchen and bar displays, Cassa, floor plan, reservations, finance and website builder."),
        ("Contact", "contact", contact(), False, "canvas", "restaurant software",
         "Get ODG-RESTAURANT for your restaurant, bar or café in Curaçao. Contact Oliver Dean Group."),
    ]):
        layout = clean_layout(layout)
        page, created = Page.objects.get_or_create(slug=slug, defaults={"title": title})
        if created or not page.revisions.exists():
            page.title, page.layout, page.editor, page.status = title, layout, Page.Editor.BUILDER, Page.Status.PUBLISHED
            page.is_homepage, page.template, page.order, page.focus_keyword, page.meta_description = is_home, tpl, i, kw, desc
            page.meta_title = "ODG-RESTAURANT — the restaurant system for Curaçao" if is_home else ""
            page.save()
        made.append(page)
    menu = Menu.objects.create(name="Main menu", location=Menu.Location.HEADER)
    for i, (label, page, url) in enumerate([
        ("Home", made[0], ""), ("Features", made[1], ""), ("Live demo", None, "/demo/"),
        ("Demo restaurant", None, "/demo/site/"), ("Contact", made[2], ""),
    ]):
        MenuItem.objects.create(menu=menu, label=label, page=page, url=url, order=i)

    look = Appearance.load()
    look.theme = "modern"
    look.primary_color, look.secondary_color, look.accent_color = NAVY, "#c8102e", "#ffc800"
    look.background_color, look.text_color = "#ffffff", "#1c2133"
    look.heading_font, look.body_font = "Poppins", "Inter"
    look.header_layout, look.header_topbar, look.header_sticky = "left", False, True
    look.header_cta_text, look.header_cta_link = "Try the demo", "/demo/"
    look.hero_enabled = False
    look.radius = 12
    look.footer_layout = clean_layout(footer())
    look.footer_text = "Oliver Dean Group"
    look.footer_show_powered = False
    look.save()

    brand = Brand.load()
    brand.name, brand.short_name = "ODG-RESTAURANT", "ODG-RESTAURANT"
    brand.motto = "The restaurant system for Curaçao"
    brand.cuisine, brand.opening_hours = "", ""
    if not brand.logo:
        logo = settings.BASE_DIR / "static" / "odg" / "img" / "odg-restaurant.svg"
        with open(logo, "rb") as fh:
            brand.logo.save("odg-restaurant.svg", File(fh), save=False)
    brand.save()

    seo = SEOSettings.load()
    seo.site_title = "ODG-RESTAURANT"
    seo.meta_description = ("The restaurant system for Curaçao: live POS, bar & kitchen screens, Cassa, reservations, "
                            "finance and a website builder. English, Dutch and Spanish.")
    seo.schema_type = "Organization"
    seo.save()
    return made
