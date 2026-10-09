"""Screenshots of the dashboard at phone and tablet sizes, for checking the layout.

    .venv\\Scripts\\python tools\\review.py [base-url]
Output: data/review/<size>-<page>.jpg (not part of the website).
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
OUT = Path(__file__).resolve().parent.parent / "data" / "review"
SIZES = {"phone": (390, 844), "tab-p": (800, 1280), "tab-l": (1280, 800)}
PAGES = [
    ("waiter", "/dashboard/pos/", "tables"),
    ("waiter", "order", "order"),
    ("chef", "/dashboard/pos/kitchen/", "kitchen"),
    ("manager", "/dashboard/pos/overview/", "overview"),
    ("manager", "/dashboard/pos/cassa/", "cassa"),
    ("manager", "/dashboard/pos/floor/", "floor"),
    ("manager", "/dashboard/pos/reservations/", "reservations"),
    ("owner", "/dashboard/finance/", "finance"),
    ("owner", "/dashboard/home/", "home"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[2:])
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        for size, (w, h) in SIZES.items():
            ctx = b.new_context(viewport={"width": w, "height": h}, locale="en-US", has_touch=True, is_mobile=w < 900)
            page = ctx.new_page()
            page.goto(f"{BASE}/demo/site/?lang=en", wait_until="load")
            for role, path, name in PAGES:
                if only and name not in only:
                    continue
                page.goto(f"{BASE}/dashboard/demo/enter/?as={role}", wait_until="load")
                if path == "order":
                    page.goto(f"{BASE}/dashboard/pos/", wait_until="load")
                    page.locator(".ftable.st-busy").first.click()
                else:
                    page.goto(BASE + path, wait_until="load")
                if name == "cassa":
                    page.locator(".cassa-list a.billing").first.click()
                page.wait_for_timeout(1200)
                page.screenshot(path=str(OUT / f"{size}-{name}.jpg"), type="jpeg", quality=60, full_page=False)
            ctx.close()
        b.close()
    print("ok", OUT)


if __name__ == "__main__":
    main()
