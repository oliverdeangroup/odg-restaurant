"""Starter website: pages built with the drag & drop builder + a footer.

Used by `setup_odg` (real restaurant, only when there are no pages yet) and
by the demo restaurant.
"""
from .models import Appearance, Menu, MenuItem, Page

_n = [0]


def _id(prefix):
    _n[0] += 1
    return f"{prefix}{_n[0]}"


def w(type_, **data):
    return {"id": _id("w"), "type": type_, "data": data}


def sec(layout, *columns, **style):
    st = {"bg": "", "image": "", "overlay": 0, "padding": "md", "width": "boxed", "align": "left", "dark": False, "anchor": ""}
    st.update(style)
    return {"id": _id("s"), "layout": layout, "style": st, "columns": [{"widgets": list(c)} for c in columns]}


REVIEWS = [
    {"name": "Maria G.", "rating": 5, "text": "The best sunset dinner on the island. The fish of the day was perfect and the staff made us feel at home.", "source": "Google"},
    {"name": "Kevin & Sanne", "rating": 5, "text": "Booked online in one minute. Great cocktails, friendly service and a lovely table on the terrace.", "source": "TripAdvisor"},
    {"name": "Jonathan R.", "rating": 4, "text": "Delicious keshi yená and a very good pepper steak. We will definitely come back.", "source": "Google"},
]


def home_layout(name):
    return {"sections": [
        sec("1", [w("hero", title=f"Welcome to {name}", subtitle="Fresh local fish, grilled meat and island cocktails. Lunch and dinner every day.",
                    button_text="Book a table", button_link="/reservations/", button2_text="View the menu", button2_link="/menu/",
                    image="", overlay=45, height="lg", align="center")], padding="none", width="full"),
        sec("1-1", [w("heading", text="Our story", level="h2", align="left", sub="Since 2010"),
                    w("text", html="<p>We cook with fresh products from local fishermen and farmers. Every dish is made to order, "
                                   "from our famous pepper steak to the catch of the day.</p><p>Sit inside in our cosy dining room or "
                                   "outside on the terrace with a view of the sea.</p>", align="left"),
                    w("button", text="About us", link="/about-us/", style="outline", align="left", new_tab=False)],
            [w("image", src="", alt="Our restaurant", link="", caption="", rounded=True, width="100")], padding="lg"),
        sec("1-1-1", [w("icon_box", icon="fish", title="Fresh every day", text="Fish and vegetables bought fresh every morning.", align="center")],
            [w("icon_box", icon="glass", title="Island cocktails", text="Our bartenders mix the classics and their own creations.", align="center")],
            [w("icon_box", icon="calendar", title="Book online", text="Choose your time and table in seconds, 24/7.", align="center")],
            padding="md", bg="#f4ede2"),
        sec("1", [w("heading", text="From our menu", level="h2", align="center", sub=""),
                  w("menu", categories=[], show_prices=True, show_images=True, show_descriptions=True, columns="2", title="")], padding="lg"),
        sec("1", [w("reviews", items=REVIEWS, title="What our guests say", columns="3")], padding="lg", bg="#f4ede2"),
        sec("1-1", [w("reservation", title="Book your table", text="Choose a date, the number of guests and a time. You receive a confirmation right away.")],
            [w("hours", title="Opening hours"), w("map", query="", height=280)], padding="lg", anchor="book"),
    ]}


def menu_layout():
    return {"sections": [
        sec("1", [w("heading", text="Our menu", level="h1", align="center", sub="Food & drinks"),
                  w("text", html="<p style=\"text-align:center\">Tell us about allergies: our chefs are happy to help.</p>", align="center"),
                  w("menu", categories=[], show_prices=True, show_images=True, show_descriptions=True, columns="2", title="")], padding="lg"),
    ]}


def reservations_layout():
    return {"sections": [
        sec("2-1", [w("reservation", title="Book a table", text="Reservations online are possible up to a few hours in advance. For groups please call us.")],
            [w("hours", title="Opening hours"), w("contact", title="Questions?", show_social=True)], padding="lg"),
    ]}


def about_layout(name):
    return {"sections": [
        sec("1-1", [w("heading", text="About us", level="h1", align="left", sub=name),
                    w("text", html="<p>What started as a small beach bar is now a restaurant where locals and visitors meet. "
                                   "Our team of chefs, bartenders and waiters works every day to give you a great evening.</p>"
                                   "<p>We are proud to work with local suppliers and to bring the flavours of Curaçao to your table.</p>", align="left")],
            [w("image", src="", alt="Our team", link="", caption="", rounded=True, width="100")], padding="lg"),
        sec("1", [w("gallery", images=[], columns="3")], padding="md"),
    ]}


def contact_layout():
    return {"sections": [
        sec("1-1", [w("heading", text="Contact", level="h1", align="left", sub="We look forward to seeing you"),
                    w("contact", title="", show_social=True), w("hours", title="Opening hours")],
            [w("map", query="", height=420)], padding="lg"),
    ]}


def footer_layout(name):
    return {"sections": [
        sec("1-1-1",
            [w("heading", text=name, level="h3", align="left", sub=""),
             w("text", html="<p>Fresh food, island flavours and a warm welcome.</p>", align="left"), w("social", align="left")],
            [w("contact", title="Contact", show_social=False)],
            [w("hours", title="Opening hours"), w("button", text="Book a table", link="/reservations/", style="primary", align="left", new_tab=False)],
            padding="lg", dark=True, bg="#1d1714"),
    ]}


def create(name="My Restaurant"):
    """Creates the starter pages, menus and footer. Returns False when pages exist."""
    if Page.objects.exists():
        return False
    pages = [
        ("Home", "home", home_layout(name), True, "landing", "restaurant Curaçao"),
        ("Menu", "menu", menu_layout(), False, "canvas", "menu"),
        ("Reservations", "reservations", reservations_layout(), False, "default", "book a table"),
        ("About us", "about-us", about_layout(name), False, "canvas", "about"),
        ("Contact", "contact", contact_layout(), False, "canvas", "contact"),
    ]
    made = []
    for i, (title, slug, layout, home, tpl, kw) in enumerate(pages):
        made.append(Page.objects.create(
            title=title, slug=slug, layout=layout, editor=Page.Editor.BUILDER, status=Page.Status.PUBLISHED,
            is_homepage=home, template=tpl, order=i, focus_keyword=kw,
            meta_description=f"{name} — {title.lower()}: fresh food, cocktails and online table reservations in Curaçao."[:160],
        ))
    menu = Menu.objects.create(name="Main menu", location=Menu.Location.HEADER)
    for i, p in enumerate(made):
        MenuItem.objects.create(menu=menu, label=p.title, page=p, order=i)
    look = Appearance.load()
    if not look.footer_layout:
        look.footer_layout = footer_layout(name)
        look.save(update_fields=["footer_layout"])
    return True
