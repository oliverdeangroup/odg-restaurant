# ODG-RESTAURANT

Restaurant management system: a real-time POS (waiters, bar, kitchen, Cassa), floor plan,
reservations, customers, finance, and a website with a drag & drop builder.
Built with Django (Python), MySQL and LiteSpeed on the cPanel server, the same way as ODG-SCHOOL.
The interface is in **English, Dutch and Spanish** (switch EN / NL / ES at the top).

## Roles and dashboards

| Role | Sees |
|---|---|
| **Administrator** | Everything: website builder, POS configuration, users, finance, settings, updates, all history and the activity log. Can view Cassa and its history but does not take payments. |
| **Moderator** | Like the administrator, except Updates, System users and Settings. |
| **Owner** (only 1) | Full overview, finance and PDF reports, live POS, Cassa, floor, reservations, history. |
| **Manager** (max 2, set in Settings) | Live POS and Cassa, all orders, floor, reservations, history of the last 7 days (set in Settings → POS), staff performance. |
| **Waiter** | Floor with table status, take orders per table and per guest (Guest #1, #2 …), pick-up alerts, mark items as served, request the bill. |
| **Bartender** | Live drink queue with timers; marks drinks as completed. |
| **Chef** | Live kitchen queue with preparation details (doneness, pasta type, notes); marks dishes as completed. |

Customers are internal profiles (customer ID like `C000042`, name, e-mail, phone/WhatsApp,
reservation history, past orders, table history). They are not user logins.

## How an order moves (real time)

1. The waiter opens a table and adds items per guest, with options (e.g. *Doneness: Medium rare*) and notes.
2. **Submit to bar & kitchen** splits the items automatically: drinks → bartender, food → chef.
3. Bar and kitchen see tickets with table, guest numbers, items, preparation details, time submitted and estimated time.
   Tickets turn yellow when due and red when late. Completed items leave the live queue.
4. The waiter gets a notification (toast + sound) to pick up, then marks the items as **Served**.
5. All screens update by themselves every 3 seconds (Settings → POS). The green **LIVE** dot shows the connection.
6. **Cassa** (manager / owner): split by guest, discount, tip (with % buttons), cash (with change) or card,
   bill in 80 mm, A5 or A4. Pro-forma bills and receipts are saved as PDF; receipts are numbered without gaps.
   After **Paid / Checkout** the table is free again.

Each order has a unique code **YYYYMMDDHH + table number**, digits only (e.g. `20261008194`). If the same table
opens twice in one hour a digit is added, so codes are always unique.

**Order history** shows the last 90 days (day / week / month filters). Older orders are not deleted: paid
orders, payments and bills are kept because Curaçao requires 10 years of bookkeeping.

## Other parts

- **Products**: categories in a tree (Beverages → Alcohol → Cocktails → Long Island). The station (bar or kitchen)
  is set on the top category. Products have price, preparation time, options, photo, and a "sold out today" switch.
- **Floor manager**: drag & drop designer with rectangle and round tables, sections (e.g. Section 1 left, Section 2 right),
  a live colour-coded floor for everyone, a mini reservation timeline per table and a full timeline.
- **Table reservation**: day / week / month view, first name, last name, phone, table, guests; click a name for the
  customer profile. Online bookings from the website use 30-minute slots, a minimum number of hours in advance, and
  only free tables. A table with an open order stays unavailable until Cassa marks it paid.
- **Finance**: Profit & Loss per day, week, month and year; OB (sales tax) collected minus OB on expenses; tips shown
  separately; expenses; day close (Z report with cash count); CSV export for the accountant; PDF reports with the
  restaurant logo in the header and contact details in the footer. Currency default: XCG (Caribbean guilder, Cg) and OB 6 %.
  **Check the OB rate and bookkeeping rules with your accountant.**
- **Website**: drag & drop page builder (sections, columns and widgets: heading, text, image, button, hero, gallery,
  video, Google Maps, reviews, food & drinks menu from POS, online reservation, opening hours, contact, social, HTML),
  an HTML editor, a header builder (3 layouts) and a footer builder, 3 themes (Bistro, Modern, Lounge) that never touch
  the data, Pages, Menu (with submenus), Brand, SEO (Rank Math-style score per page, sitemap.xml, robots.txt,
  schema.org Restaurant data, redirects) and a media library.
- **Updates**: Settings → Updates → upload a ZIP. A backup is made first, user data is never touched, and a failed
  update is rolled back automatically.
- **Public demo** at `/demo/`: no login, one private copy per visitor (cookie, or IP address), with the waiter,
  bartender, chef, manager and owner dashboards (not the administrator). Visitors switch role in the yellow bar.
  Copies are removed 24 h after the last visit; all times are moved to "now" so the demo always looks live.

## Working on your PC

```bash
.venv\Scripts\activate
python manage.py runserver
```

Open http://127.0.0.1:8000. The local test login is in `DEV-LOGINS.txt` (only on your PC, never uploaded).

| Command | What it does |
|---|---|
| `python manage.py test` | Runs the built-in checks (order flow, permissions, booking, demo isolation) |
| `python manage.py setup_odg --admin NAME --email E` | First-time setup: categories, a starter floor and website (safe to run again) |
| `python manage.py demo_build` | Rebuilds the public demo restaurant (also done by every update) |
| `python manage.py make_update 1.1.0 --notes "..."` | Builds an update ZIP in `dist/` |
| `python manage.py i18n_strings` | Lists texts that still need Dutch / Spanish |

Translations: `core/translations.py` and `core/translations_restaurant.py`.

## Server

See [deploy/INSTALL.md](deploy/INSTALL.md).

## Folder layout

```
core/      users, roles, home, settings, updates, translations, demo
pos/       POS: products, floor, orders, bar/kitchen, Cassa, bills (PDF), reservations, customers
finance/   expenses, Profit & Loss, PDF report, CSV export
website/   pages + drag & drop builder, themes, menus, brand, SEO, media, online booking
templates/ all screens (website/themes and website/widgets = the public site)
static/    CSS and JavaScript (live.js = real-time sync, order.js, builder.js, floor-design.js)
deploy/    server files (gunicorn, systemd, .htaccess, INSTALL.md)
```
