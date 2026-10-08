"""Fills the demo template: a complete restaurant with staff, menu, floor,
customers, reservations, two months of paid orders, expenses and a busy
"right now" (open tables in every state).

All names are fictional. Runs inside `core.demo.use(...)`, so everything is
written to the demo copy, never to the real database. Returns the build time:
copies shift all dates so that this moment becomes "now".
"""
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from core.management.commands.setup_odg import make_categories
from core.models import Notification, Role, SystemSettings, User
from finance.models import Expense
from pos.models import (
    Category, Customer, DayClose, Order, OrderItem, Payment, PosSettings, Product, Reservation, Section, Station, Table, money,
)
from website import starter
from website.models import Appearance, Brand, SEOSettings

R = random.Random(2026)
DAYS = 60

STAFF = [
    ("demo.waiter", "Luis", "Martina", Role.WAITER),
    ("demo.bartender", "Shanty", "Isenia", Role.BARTENDER),
    ("demo.chef", "Marco", "Doran", Role.CHEF),
    ("demo.manager", "Diana", "Pieters", Role.MANAGER),
    ("demo.owner", "Jeanette", "Croes", Role.OWNER),
    ("demo.waiter2", "Kevin", "Leito", Role.WAITER),
    ("demo.waiter3", "Naomi", "Rosaria", Role.WAITER),
    ("demo.chef2", "Ruben", "Sint Jago", Role.CHEF),
]

# (category path, name, price, prep minutes, options, description)
MENU = [
    ("Beverages/Soft Drinks", "Cola Zero", "5.50", 2, "", ""),
    ("Beverages/Soft Drinks", "Coca-Cola", "5.50", 2, "", ""),
    ("Beverages/Soft Drinks", "Fresh lemonade", "7.00", 4, "*Ice: With ice | No ice", "Homemade with lime and mint"),
    ("Beverages/Soft Drinks", "Passion fruit juice", "8.00", 3, "", "Fresh tropical juice"),
    ("Beverages/Soft Drinks", "Mineral water", "4.50", 1, "*Type: Still | Sparkling", ""),
    ("Beverages/Alcohol/Cocktails", "Long Island", "18.00", 6, "", "Vodka, gin, rum, tequila, triple sec and cola"),
    ("Beverages/Alcohol/Cocktails", "Blue Curaçao Lagoon", "16.00", 5, "", "Our signature cocktail with Blue Curaçao"),
    ("Beverages/Alcohol/Cocktails", "Mojito", "15.00", 5, "Sugar: Normal | Less sweet", "Rum, mint, lime and soda"),
    ("Beverages/Alcohol/Cocktails", "Piña Colada", "15.00", 5, "", "Rum, coconut and pineapple"),
    ("Beverages/Alcohol/Beer", "Polar", "6.50", 1, "", "Local favourite"),
    ("Beverages/Alcohol/Beer", "Amstel Bright", "6.50", 1, "", ""),
    ("Beverages/Alcohol/Wine", "House wine (glass)", "11.00", 1, "*Colour: Red | White | Rosé", ""),
    ("Beverages/Coffee & Tea", "Espresso", "4.50", 2, "", ""),
    ("Beverages/Coffee & Tea", "Cappuccino", "6.00", 3, "Milk: Regular | Oat", ""),
    ("Food/Appetizers", "Onion Rings", "11.00", 8, "", "Crispy, with garlic dip"),
    ("Food/Appetizers", "Pastechi trio", "12.50", 8, "", "Cheese, chicken and beef"),
    ("Food/Appetizers", "Fish soup", "14.00", 6, "", "Caribbean style with fresh fish"),
    ("Food/Appetizers", "Caesar salad", "15.00", 7, "Extra: None | Chicken | Shrimps", ""),
    ("Food/Main Course/Meat", "Pepper Steak", "42.00", 18, "*Doneness: Rare | Medium rare | Medium | Well done\n*Side: Fries | Rice | Funchi | Salad", "Tenderloin with green pepper sauce"),
    ("Food/Main Course/Meat", "Keshi yená", "34.00", 16, "*Side: Rice | Funchi | Fries", "Traditional stuffed cheese with chicken"),
    ("Food/Main Course/Meat", "BBQ ribs", "36.00", 17, "*Side: Fries | Rice | Salad", "Slow cooked, island BBQ sauce"),
    ("Food/Main Course/Meat", "Chicken satay", "29.00", 14, "*Side: Fries | Rice", "With peanut sauce"),
    ("Food/Main Course/Fish", "Catch of the day", "44.00", 18, "*Preparation: Grilled | Fried\n*Side: Funchi | Rice | Fries", "Fresh local fish, creole sauce"),
    ("Food/Main Course/Fish", "Garlic shrimps", "39.00", 14, "*Side: Rice | Fries | Salad", ""),
    ("Food/Main Course/Vegetarian", "Pasta primavera", "27.00", 14, "*Pasta: Penne | Spaghetti | Tagliatelle", "Seasonal vegetables, parmesan"),
    ("Food/Main Course/Vegetarian", "Veggie curry", "26.00", 15, "*Spice: Mild | Medium | Hot", "Coconut curry with rice"),
    ("Food/Side Dish", "Fries", "6.00", 6, "", ""),
    ("Food/Side Dish", "Funchi fries", "7.00", 7, "", "Crispy cornmeal fries"),
    ("Food/Side Dish", "Fried plantain", "6.50", 6, "", ""),
    ("Food/Desserts", "Quesillo", "11.00", 4, "", "Caribbean caramel flan"),
    ("Food/Desserts", "Chocolate lava cake", "13.00", 9, "Ice cream: Vanilla | Coconut | None", ""),
    ("Food/Desserts", "Bolo di cashupete", "12.00", 4, "", "Local cashew cake"),
]

FIRST = ["Anna", "Mark", "Sophie", "Ricardo", "Elena", "Tom", "Lisa", "Carlos", "Mila", "Jorge", "Eva", "Daan", "Sara",
         "Pedro", "Noa", "Bas", "Julia", "Ivan", "Maria", "Lucas", "Emma", "Sem", "Chantal", "Ruben", "Iris", "Jayden", "Nina"]
LAST = ["Martis", "de Vries", "Gomez", "Hoek", "Rojer", "Jansen", "Felida", "Suarez", "Meyer", "Bakker", "Sillé", "Visser",
        "Pinedo", "Smits", "Ricardo", "Statia", "Mulder", "Fernandes", "Koster", "Winklaar", "Brouwer", "Rivas"]

TABLES = [  # number, section index, shape, seats, x, y, w, h
    (1, 0, "rect", 4, 60, 70, 110, 90), (2, 0, "rect", 4, 240, 70, 110, 90), (3, 0, "round", 2, 420, 75, 90, 90),
    (4, 0, "rect", 6, 60, 250, 150, 90), (5, 0, "round", 4, 280, 245, 100, 100), (6, 0, "round", 2, 440, 255, 80, 80),
    (7, 0, "rect", 4, 60, 430, 110, 90), (8, 0, "rect", 8, 240, 430, 200, 100),
    (9, 1, "rect", 2, 660, 70, 90, 80), (10, 1, "rect", 2, 800, 70, 90, 80), (11, 1, "rect", 4, 950, 70, 110, 90),
    (12, 1, "round", 4, 680, 260, 100, 100), (13, 1, "round", 6, 870, 250, 130, 130), (14, 1, "rect", 4, 680, 450, 110, 90),
    (15, 1, "rect", 10, 860, 450, 240, 100),
]


def _aware(d, h, m=0):
    return timezone.make_aware(datetime.combine(d, time(h, m)))


def seed():
    now = timezone.now()
    today = timezone.localdate()

    # ---------------------------------------------------------- settings & brand
    s = SystemSettings.load()
    s.demo_enabled = True
    s.session_timeout_minutes = 0
    s.save()
    b = Brand.load()
    b.name, b.short_name, b.motto = "Seaside Grill", "Seaside Grill", "Fresh food, island flavours"
    b.address, b.city, b.country = "Penstraat 12", "Willemstad", "Curaçao"
    b.phone, b.whatsapp, b.email = "+599 9 461 0000", "+599 9 461 0000", "hello@seaside-grill.example"
    b.opening_hours = "Mon–Sun 12:00 – 22:00"
    b.save()
    ps = PosSettings.load()
    ps.crib_number, ps.kvk_number = "DEMO-123456", "DEMO-98765"
    ps.opening_hours = {str(d): ["12:00", "22:00"] for d in range(7)}
    ps.min_hours_ahead = 1
    ps.save()
    look = Appearance.load()
    look.theme = "bistro"
    look.save()
    SEOSettings.load()

    # ---------------------------------------------------------- staff
    users = {}
    for username, first, last, role in STAFF:
        u = User(username=username, first_name=first, last_name=last, role=role, language="",
                 email=f"{username.replace('demo.', '')}@seaside-grill.example")
        u.set_unusable_password()
        u.save()
        users[username] = u
    waiters = [users["demo.waiter"], users["demo.waiter2"], users["demo.waiter3"]]
    chefs = [users["demo.chef"], users["demo.chef2"]]
    bartender = users["demo.bartender"]
    manager = users["demo.manager"]

    # ---------------------------------------------------------- menu
    make_categories()
    cats = {}
    for c in Category.objects.all():
        cats[c.path.replace(" → ", "/")] = c
    products = []
    for i, (path, name, price, prep, opts, desc) in enumerate(MENU):
        products.append(Product(category=cats[path], name=name, price=Decimal(price), prep_minutes=prep,
                                options_text=opts, description=desc, order=i))
    Product.objects.bulk_create(products)
    products = list(Product.objects.select_related("category__parent__parent"))
    by_name = {p.name: p for p in products}
    drinks = [p for p in products if p.resolved_station == Station.BAR]
    starters = [p for p in products if p.category.name == "Appetizers"]
    mains = [p for p in products if p.category.parent and p.category.parent.name == "Main Course"]
    sides = [p for p in products if p.category.name == "Side Dish"]
    desserts = [p for p in products if p.category.name == "Desserts"]

    # ---------------------------------------------------------- floor
    secs = [Section.objects.create(name="Terrace", color="#e8f1ea", x=20, y=20, w=560, h=700, order=0),
            Section.objects.create(name="Dining room", color="#eaeef8", x=620, y=20, w=560, h=700, order=1)]
    tables = {}
    for n, si, shape, seats, x, y, w, h in TABLES:
        tables[n] = Table.objects.create(number=n, section=secs[si], shape=shape, seats=seats, x=x, y=y, w=w, h=h,
                                         online_bookable=n != 15)

    # ---------------------------------------------------------- customers
    customers = []
    used = set()
    for i in range(70):
        f, last = R.choice(FIRST), R.choice(LAST)
        email = f"{f}.{last}".lower().replace(" ", "") + (f"{i}" if (f, last) in used else "") + "@example.com"
        used.add((f, last))
        customers.append(Customer(number=i + 1, first_name=f, last_name=last, email=email,
                                  phone=f"+599 9 5{R.randint(10, 99)} {R.randint(1000, 9999)}",
                                  notes=R.choice(["", "", "", "Allergic to nuts", "Prefers the terrace", "Birthday in March", "Vegetarian"]),
                                  created_at=now - timedelta(days=R.randint(1, 400))))
    Customer.objects.bulk_create(customers)
    customers = list(Customer.objects.all())

    # ---------------------------------------------------------- history (paid orders)
    s_cfg = PosSettings.load()

    def calc(lines, discount=Decimal("0")):
        sub = money(sum((p * q for p, q in lines), Decimal("0")))
        total = sub - discount
        tax = money(total * s_cfg.tax_rate / (100 + s_cfg.tax_rate))
        return sub, money(total), tax

    orders, items_by_order, pays_by_order = [], {}, {}
    codes = set()
    for back in range(DAYS, -1, -1):
        day = today - timedelta(days=back)
        weekend = day.weekday() >= 4
        n = R.randint(22, 34) if weekend else R.randint(14, 24)
        if back == 0:
            n = 0  # today is built below, relative to "now"
        for _ in range(n):
            t = tables[R.choice(list(tables))]
            opened = _aware(day, R.choice([12, 12, 13, 13, 14, 18, 18, 19, 19, 19, 20, 20, 21]), R.randint(0, 59))
            guests = max(1, min(t.seats, R.choice([1, 2, 2, 2, 3, 4, 4, 5, 6])))
            base = f"{timezone.localtime(opened):%Y%m%d%H}{t.number}"
            code, k = base, 2
            while code in codes:
                code, k = f"{base}{k}", k + 1
            codes.add(code)
            o = Order(code=code, table=t, table_number=t.number, waiter=R.choice(waiters), guests=guests,
                      customer=R.choice(customers) if R.random() < 0.35 else None, opened_at=opened, status=Order.Status.PAID)
            its = []
            for g in range(1, guests + 1):
                picks = [(R.choice(drinks), 1)]
                if R.random() < 0.4:
                    picks.append((R.choice(drinks), 1))
                if R.random() < 0.35:
                    picks.append((R.choice(starters), 1))
                picks.append((R.choice(mains), 1))
                if R.random() < 0.2:
                    picks.append((R.choice(sides), 1))
                for p, q in picks:
                    its.append((p, q, g, 1))
                if R.random() < 0.3:
                    its.append((R.choice(desserts), 1, g, 2))
            items_by_order[code] = its
            orders.append(o)
    Order.objects.bulk_create(orders)
    orders = {o.code: o for o in Order.objects.all()}
    all_items, all_pays = [], []
    for code, o in orders.items():
        lines = []
        for p, q, g, batch in items_by_order[code]:
            sub_at = o.opened_at + timedelta(minutes=3 if batch == 1 else R.randint(50, 65))
            prep = max(1, p.prep_minutes + R.randint(-3, 6))
            ready = sub_at + timedelta(minutes=prep)
            served = ready + timedelta(minutes=R.randint(1, 4))
            st = p.resolved_station
            opts = []
            for grp in p.options:
                if grp["required"] or R.random() < 0.5:
                    opts.append(f"{grp['name']}: {R.choice(grp['choices'])}")
            all_items.append(OrderItem(
                order=o, product=p, name=p.name, category_name=p.category.path, station=st, guest_no=g, qty=q,
                unit_price=p.price, options=opts, status=OrderItem.Status.SERVED, batch=batch, est_minutes=p.prep_minutes,
                paid=True, submitted_at=sub_at, ready_at=ready, served_at=served, added_by=o.waiter,
                prepared_by=bartender if st == Station.BAR else R.choice(chefs), served_by=o.waiter,
            ))
            lines.append((p.price, q, g))
        paid_at = o.opened_at + timedelta(minutes=R.randint(70, 115))
        method = Payment.Method.CARD if R.random() < 0.62 else Payment.Method.CASH
        split = o.guests >= 2 and R.random() < 0.15
        groups = {}
        for price, q, g in lines:
            groups.setdefault(g if split else None, []).append((price, q))
        for g, gl in groups.items():
            sub, total, tax = calc(gl)
            tip = money(total * Decimal(R.choice([0, 0, 5, 10, 10, 12, 15])) / 100)
            received = total + tip if method == Payment.Method.CARD else money((total + tip + 4) // 5 * 5)
            all_pays.append(Payment(order=o, guest_no=g, method=method, subtotal=sub, discount=0, service_charge=0,
                                    amount=total, tax_amount=tax, tip=tip, received=received,
                                    change=money(received - total - tip), bill_number="", paid_at=paid_at, received_by=manager))
    OrderItem.objects.bulk_create(all_items, batch_size=500)
    all_pays.sort(key=lambda p: p.paid_at)
    for i, p in enumerate(all_pays, start=1):
        p.bill_number = f"{i:06d}"
    Payment.objects.bulk_create(all_pays, batch_size=500)
    # Order totals from the payments
    totals = {}
    for p in all_pays:
        t = totals.setdefault(p.order_id, {"sub": 0, "tax": 0, "tip": 0, "total": 0, "closed": p.paid_at, "bills": []})
        t["sub"] += p.subtotal
        t["tax"] += p.tax_amount
        t["tip"] += p.tip
        t["total"] += p.amount
        t["closed"] = max(t["closed"], p.paid_at)
        t["bills"].append(p.bill_number)
    upd = []
    for o in orders.values():
        t = totals[o.pk]
        o.subtotal, o.tax_amount, o.tip, o.total = money(t["sub"]), money(t["tax"]), money(t["tip"]), money(t["total"])
        o.closed_at, o.tax_rate, o.paid_by = t["closed"], s_cfg.tax_rate, manager
        o.bill_number = t["bills"][0] if len(t["bills"]) == 1 else f"{t['bills'][0]}…{t['bills'][-1]}"
        upd.append(o)
    Order.objects.bulk_update(upd, ["subtotal", "tax_amount", "tip", "total", "closed_at", "tax_rate", "paid_by", "bill_number"], batch_size=500)
    s_cfg.next_bill_number = len(all_pays) + 1
    s_cfg.save()

    # ---------------------------------------------------------- day closes & expenses
    closes = []
    for back in range(DAYS, 0, -1):
        day = today - timedelta(days=back)
        day_pays = [p for p in all_pays if timezone.localtime(p.paid_at).date() == day]
        if not day_pays:
            continue
        cash = money(sum((p.amount + p.tip for p in day_pays if p.method == "cash"), Decimal("0")))
        card = money(sum((p.amount + p.tip for p in day_pays if p.method == "card"), Decimal("0")))
        exp = Decimal("300.00") + cash
        diff = Decimal(R.choice([0, 0, 0, 0, -5, 5, -10]))
        closes.append(DayClose(date=day, opening_cash=Decimal("300.00"), expected_cash=exp, counted_cash=exp + diff,
                               card_total=card, sales_total=money(sum((p.amount for p in day_pays), Decimal("0"))),
                               tips_total=money(sum((p.tip for p in day_pays), Decimal("0"))), closed_by=manager,
                               closed_at=_aware(day, 23, 10), note="" if not diff else "Small difference"))
    DayClose.objects.bulk_create(closes)
    exps = []
    for back in range(DAYS, -1, -1):
        day = today - timedelta(days=back)
        if day.weekday() in (0, 3):
            amt = Decimal(R.randint(1400, 2600))
            exps.append(Expense(date=day, category="food", description="Fish, meat and vegetables", supplier="Island Fresh Foods",
                                amount=amt, tax_amount=money(amt * 6 / 106), method="bank", created_by=manager))
        if day.weekday() == 1:
            amt = Decimal(R.randint(700, 1300))
            exps.append(Expense(date=day, category="drinks", description="Beverages and spirits", supplier="Caribbean Drinks Co.",
                                amount=amt, tax_amount=money(amt * 6 / 106), method="bank", created_by=manager))
        if day.day == 1:
            exps.append(Expense(date=day, category="rent", description="Rent restaurant", supplier="Penstraat Real Estate",
                                amount=Decimal("6500.00"), tax_amount=0, method="bank", created_by=manager))
            exps.append(Expense(date=day, category="utilities", description="Aqualectra water & electricity", supplier="Aqualectra",
                                amount=Decimal(R.randint(1800, 2400)), tax_amount=0, method="bank", created_by=manager))
        if day.day in (15, 28):
            exps.append(Expense(date=day, category="wages", description="Salaries staff", supplier="",
                                amount=Decimal("9800.00"), tax_amount=0, method="bank", created_by=manager))
        if day.day == 10:
            exps.append(Expense(date=day, category="fees", description="Card terminal fees", supplier="Bank",
                                amount=Decimal(R.randint(250, 420)), tax_amount=0, method="bank", created_by=manager))
    Expense.objects.bulk_create(exps)

    # ---------------------------------------------------------- reservations
    res = []
    for back in range(DAYS, 0, -1):
        day = today - timedelta(days=back)
        for _ in range(R.randint(2, 6)):
            t = tables[R.choice(list(tables))]
            res.append(Reservation(customer=R.choice(customers), table=t, start=_aware(day, R.choice([12, 13, 18, 19, 19, 20]), R.choice([0, 30])),
                                   guests=min(t.seats, R.randint(2, 6)), status=R.choice(["completed"] * 8 + ["no_show", "cancelled"]),
                                   source=R.choice(["phone", "website", "website", "staff"]), created_at=now - timedelta(days=back + 3)))
    for ahead in range(1, 15):
        day = today + timedelta(days=ahead)
        for _ in range(R.randint(2, 7)):
            t = tables[R.choice([1, 2, 3, 5, 6, 9, 10, 11, 12, 13, 14])]
            res.append(Reservation(customer=R.choice(customers), table=t, start=_aware(day, R.choice([12, 13, 18, 19, 20]), R.choice([0, 30])),
                                   guests=min(t.seats, R.randint(2, 5)), status=R.choice(["confirmed", "confirmed", "pending"]),
                                   source=R.choice(["phone", "website"]), created_at=now - timedelta(days=R.randint(0, 5))))
    Reservation.objects.bulk_create(res)

    # ---------------------------------------------------------- right now
    def ago(minutes):
        return now - timedelta(minutes=minutes)

    def live(table_no, opened_min, guests, waiter, lines, status=Order.Status.OPEN, customer=None):
        t = tables[table_no]
        o = Order.objects.create(code=f"live{table_no}", table=t, table_number=t.number, waiter=waiter, guests=guests,
                                 opened_at=ago(opened_min), status=status, customer=customer)
        for name, guest, state, sub_min, opts, note in lines:
            p = by_name[name]
            it = OrderItem(order=o, product=p, name=p.name, category_name=p.category.path, station=p.resolved_station,
                           guest_no=guest, qty=1, unit_price=p.price, options=opts, notes=note, est_minutes=p.prep_minutes,
                           submitted_at=ago(sub_min), added_by=waiter, status=state)
            if state in ("preparing",):
                it.started_at = ago(max(sub_min - 2, 0))
            if state in ("ready", "served"):
                it.ready_at = ago(max(sub_min - p.prep_minutes, 1))
                it.prepared_by = bartender if it.station == Station.BAR else chefs[0]
            if state == "served":
                it.served_at = ago(max(sub_min - p.prep_minutes - 2, 0))
                it.served_by = waiter
            it.save()
        return o

    luis = users["demo.waiter"]
    live(2, 58, 2, luis, [
        ("Polar", 1, "served", 55, [], ""), ("House wine (glass)", 2, "served", 55, ["Colour: White"], ""),
        ("Catch of the day", 1, "served", 50, ["Preparation: Grilled", "Side: Funchi"], ""),
        ("Pasta primavera", 2, "served", 50, ["Pasta: Penne"], ""), ("Quesillo", 0, "served", 20, [], ""),
    ], status=Order.Status.BILLING, customer=customers[3])
    o4 = live(4, 28, 4, luis, [
        ("Blue Curaçao Lagoon", 1, "served", 26, [], ""), ("Mojito", 2, "served", 26, ["Sugar: Less sweet"], ""),
        ("Coca-Cola", 3, "served", 26, [], ""), ("Fresh lemonade", 4, "served", 26, ["Ice: No ice"], ""),
        ("Pepper Steak", 1, "preparing", 16, ["Doneness: Medium rare", "Side: Fries"], ""),
        ("Pepper Steak", 2, "preparing", 16, ["Doneness: Well done", "Side: Salad"], "Sauce on the side"),
        ("Keshi yená", 3, "queued", 16, ["Side: Funchi"], ""), ("Garlic shrimps", 4, "queued", 16, ["Side: Rice"], "No garlic butter, allergy"),
    ], customer=customers[0])
    live(5, 9, 3, luis, [
        ("Long Island", 1, "queued", 3, [], ""), ("Piña Colada", 2, "queued", 3, [], ""), ("Mineral water", 3, "queued", 3, ["Type: Sparkling"], ""),
        ("Onion Rings", 0, "queued", 3, [], ""), ("Pastechi trio", 0, "queued", 3, [], ""),
    ])
    live(7, 36, 2, luis, [
        ("Amstel Bright", 1, "served", 33, [], ""), ("Passion fruit juice", 2, "served", 33, [], ""),
        ("BBQ ribs", 1, "ready", 20, ["Side: Fries"], ""), ("Veggie curry", 2, "ready", 20, ["Spice: Hot"], ""),
    ])
    live(9, 6, 2, users["demo.waiter2"], [
        ("Cappuccino", 1, "ready", 6, ["Milk: Oat"], ""), ("Espresso", 2, "ready", 6, [], ""),
    ])
    live(11, 34, 4, users["demo.waiter2"], [
        ("Polar", 1, "served", 31, [], ""), ("Polar", 2, "served", 31, [], ""), ("Coca-Cola", 3, "served", 31, [], ""), ("Cola Zero", 4, "served", 31, [], ""),
        ("Chicken satay", 1, "queued", 27, ["Side: Rice"], ""), ("Catch of the day", 2, "preparing", 27, ["Preparation: Fried", "Side: Rice"], ""),
        ("Caesar salad", 3, "queued", 27, ["Extra: Chicken"], ""), ("Funchi fries", 0, "queued", 27, [], ""),
    ])
    live(13, 14, 5, users["demo.waiter3"], [
        ("Mojito", 1, "ready", 12, [], ""), ("Mojito", 2, "ready", 12, [], ""), ("House wine (glass)", 3, "queued", 4, ["Colour: Red"], ""),
        ("House wine (glass)", 4, "queued", 4, ["Colour: Red"], ""), ("Mineral water", 5, "queued", 4, ["Type: Still"], ""),
        ("Fish soup", 0, "preparing", 8, [], ""),
    ])
    # Order codes of the live tables (YYYYMMDDHH + table)
    for o in Order.objects.filter(code__startswith="live"):
        base = f"{timezone.localtime(o.opened_at):%Y%m%d%H}{o.table_number}"
        code, k = base, 2
        while Order.objects.filter(code=code).exists():
            code, k = f"{base}{k}", k + 1
        o.code = code
        o.save(update_fields=["code"])
    # A seated reservation for table 4 and upcoming ones today
    Reservation.objects.create(customer=customers[0], table=tables[4], start=ago(35), guests=4, status="seated", source="website",
                               notes="Anniversary dinner", created_at=now - timedelta(days=4))
    Order.objects.filter(pk=o4.pk).update(reservation=Reservation.objects.filter(table=tables[4], status="seated").first())
    for mins, tno, g, cust in ((40, 1, 3, 5), (70, 3, 2, 8), (100, 12, 4, 11), (130, 14, 2, 15), (160, 6, 2, 21), (190, 10, 2, 30)):
        Reservation.objects.create(customer=customers[cust], table=tables[tno], start=now + timedelta(minutes=mins), guests=g,
                                   status="confirmed", source=R.choice(["website", "phone"]), created_at=now - timedelta(days=1))
    # Notifications for the demo waiter (items ready to pick up)
    Notification.objects.create(recipient=luis, title="Table 7: ready to pick up", message="1× BBQ ribs, 1× Veggie curry",
                                link=f"/dashboard/pos/order/{tables[7].pk}/", category="pickup", created_at=ago(1))
    Notification.objects.create(recipient=manager, title="New online reservation: Ricardo Gomez", message="4 · today",
                                link="/dashboard/pos/reservations/", category="reservation", created_at=ago(30))

    # ---------------------------------------------------------- website
    starter.create(b.name)
    return now
