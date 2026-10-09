"""The website of the demo restaurant "Dinosaur BBQ" (a fictional restaurant).

It lives inside every visitor's demo copy and is served at /demo/site/, so a
booking made on it, or a product marked "sold out" in the demo POS, shows up
on both sides right away.
"""
from website.models import Menu, MenuItem, Page
from website.starter import sec, w

HERO = "/static/odg/img/demo/bbq-hero.svg"
PIT = "/static/odg/img/demo/bbq-pit.svg"

REVIEWS = [
    {"name": "Maria G.", "rating": 5, "text": "The brisket melts in your mouth and the mac & cheese is the best on the island. Booked online in a minute.", "source": "Google"},
    {"name": "Kevin & Sanne", "rating": 5, "text": "The Dino platter for two was huge. Great cocktails, friendly team and our table was ready when we arrived.", "source": "TripAdvisor"},
    {"name": "Jonathan R.", "rating": 4, "text": "Real low & slow barbecue with a Caribbean twist. The smoked wings with honey chipotle are a must.", "source": "Google"},
]


def style(look):
    look.theme = "lounge"
    look.primary_color, look.secondary_color, look.accent_color = "#f07c2c", "#9b2915", "#f2a541"
    look.background_color, look.text_color = "#13100e", "#efe6da"
    look.heading_font, look.body_font = "DM Serif Display", "Josefin Sans"
    look.header_layout = "left"
    look.header_topbar = True
    look.header_cta_text, look.header_cta_link = "Book a table", "/reservations/"
    look.hero_enabled = False
    look.radius = 6
    look.footer_text = "Demo website made with ODG-RESTAURANT"
    look.footer_layout = {"sections": [
        sec("1-1-1",
            [w("heading", text="Dinosaur BBQ", level="h3", align="left", sub="Low & slow"),
             w("text", html="<p>Barbecue smoked for up to 14 hours over local wood, island drinks and a warm welcome.</p>", align="left"),
             w("social", align="left")],
            [w("contact", title="Contact", show_social=False)],
            [w("hours", title="Opening hours"),
             w("button", text="Book a table", link="/reservations/", style="primary", align="left", new_tab=False)],
            padding="lg", dark=True, bg="#0b0908"),
    ]}
    look.save()


def create():
    pages = [
        ("Home", "home", home(), True, "canvas", "bbq Curaçao"),
        ("Menu", "menu", menu(), False, "canvas", "bbq menu"),
        ("Reservations", "reservations", reservations(), False, "default", "book a table"),
        ("Our pit", "our-pit", about(), False, "canvas", "smoked barbecue"),
        ("Contact", "contact", contact(), False, "canvas", "contact"),
    ]
    made = []
    for i, (title, slug, layout, is_home, tpl, kw) in enumerate(pages):
        made.append(Page.objects.create(
            title=title, slug=slug, layout=layout, editor=Page.Editor.BUILDER, status=Page.Status.PUBLISHED,
            is_homepage=is_home, template=tpl, order=i, focus_keyword=kw,
            meta_description=f"Dinosaur BBQ (demo) — {title.lower()}: low & slow barbecue, island drinks and online table booking."[:160],
        ))
    menu_obj = Menu.objects.create(name="Main menu", location=Menu.Location.HEADER)
    for i, p in enumerate(made):
        MenuItem.objects.create(menu=menu_obj, label=p.title, page=p, order=i)


def home():
    return {"sections": [
        sec("1", [w("hero", title="Low & slow barbecue", subtitle="Brisket smoked for 14 hours, ribs that fall off the bone and cold drinks from the island. Welcome to Dinosaur BBQ.",
                    button_text="Book a table", button_link="/reservations/", button2_text="See the menu", button2_link="/menu/",
                    image=HERO, overlay=20, height="lg", align="center")], padding="none", width="full"),
        sec("1-1-1",
            [w("icon_box", icon="fire", title="14 hours of smoke", text="Every night our pit runs low and slow over local wood.", align="center")],
            [w("icon_box", icon="glass", title="Island bar", text="Smoky Old Fashioned, Blue Curaçao Lagoon and craft Smoke Ale.", align="center")],
            [w("icon_box", icon="calendar", title="Book in seconds", text="Pick a time online and your table is ready when you arrive.", align="center")],
            padding="lg"),
        sec("1-1",
            [w("heading", text="From the pit", level="h2", align="left", sub="Our favourites"),
             w("text", html="<p>Baby back ribs, fatty brisket, pulled pork and our famous <strong>Dino platter</strong> for two. "
                            "Everything comes with homemade sides like three-cheese mac & cheese, cornbread with honey butter and funchi fries.</p>", align="left"),
             w("button", text="Full menu", link="/menu/", style="outline", align="left", new_tab=False)],
            [w("image", src=PIT, alt="Our barbecue smoker", link="", caption="", rounded=True, width="100")],
            padding="lg", bg="#1b1512"),
        sec("1", [w("heading", text="Tonight on the menu", level="h2", align="center", sub="Smoked daily"),
                  w("menu", categories=[], show_prices=True, show_images=False, show_descriptions=True, columns="2", title="")], padding="lg"),
        sec("1", [w("reviews", items=REVIEWS, title="What our guests say", columns="3")], padding="lg", bg="#1b1512"),
        sec("1-1", [w("reservation", title="Book your table", text="Choose a date, the number of guests and a time. You get a confirmation right away.")],
            [w("hours", title="Opening hours"), w("map", query="Pietermaai, Willemstad, Curaçao", height=300)], padding="lg", anchor="book"),
    ]}


def menu():
    return {"sections": [
        sec("1", [w("hero", title="Our menu", subtitle="Smoked in house every day. Ask our team about allergies.", button_text="", button_link="",
                    button2_text="", button2_link="", image=HERO, overlay=35, height="md", align="center")], padding="none", width="full"),
        sec("1", [w("menu", categories=[], show_prices=True, show_images=False, show_descriptions=True, columns="2", title="")], padding="lg"),
    ]}


def reservations():
    return {"sections": [
        sec("2-1", [w("reservation", title="Book a table", text="Online booking for up to 10 guests. For bigger groups and the Dino platter feast, call us.")],
            [w("hours", title="Opening hours"), w("contact", title="Questions?", show_social=True)], padding="lg"),
    ]}


def about():
    return {"sections": [
        sec("1", [w("hero", title="Our pit", subtitle="Where the smoke never stops.", button_text="Book a table", button_link="/reservations/",
                    button2_text="", button2_link="", image=HERO, overlay=35, height="md", align="center")], padding="none", width="full"),
        sec("1-1", [w("heading", text="Barbecue the slow way", level="h2", align="left", sub="Since 2015"),
                    w("text", html="<p>We started with one smoker in a backyard in Pietermaai. Today our pit runs every night, "
                                   "so the brisket is ready when you are. We use local wood, our own rubs and sauces made in house.</p>"
                                   "<p>Dinosaur BBQ is a <strong>demo restaurant</strong>: everything you see here — the menu, the reservations and the "
                                   "orders — runs on ODG-RESTAURANT.</p>", align="left")],
            [w("image", src=PIT, alt="Our smoker", link="", caption="", rounded=True, width="100")], padding="lg"),
    ]}


def contact():
    return {"sections": [
        sec("1-1", [w("heading", text="Contact", level="h1", align="left", sub="Come hungry"),
                    w("contact", title="", show_social=True), w("hours", title="Opening hours")],
            [w("map", query="Pietermaai, Willemstad, Curaçao", height=420)], padding="lg"),
    ]}
