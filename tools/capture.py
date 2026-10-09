"""Screenshots and a walkthrough video of the demo, for the product website.

Run on the PC while `python manage.py runserver 127.0.0.1:8010` is running:
    .venv\\Scripts\\python tools\\capture.py
Needs `pip install playwright` (uses the installed Microsoft Edge; no download).
Output: static/odg/img/screens/*.jpg and static/odg/video/demo-tour.webm (the video is made from
the screenshots inside the browser, with captions; no ffmpeg needed)
"""
import re
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "static" / "odg" / "img" / "screens"
VIDEO = ROOT / "static" / "odg" / "video"
CLEAN = """
.demo-bar { display: none !important; }
body.is-demo .sidenav { top: var(--top-h) !important; }
body.is-demo .main { padding-top: calc(var(--top-h) + 22px) !important; }
.demo-fab, .toasts { display: none !important; }
"""


def clean(page):
    page.add_style_tag(content=CLEAN)


def table(page, number):
    page.locator(".ftable").filter(has=page.locator("b", has_text=re.compile(rf"^{number}$"))).first.click()
    page.wait_for_load_state("networkidle")


def shot(page, name, full=False, wait=1.2):
    time.sleep(wait)
    clean(page)
    time.sleep(0.3)
    page.screenshot(path=str(SHOTS / f"{name}.jpg"), type="jpeg", quality=82, full_page=full)
    print("saved", name)


def reset(page):
    """Start from a fresh demo copy, so the pictures always look the same."""
    page.goto(f"{BASE}/demo/site/?lang=en")
    as_role(page, "waiter", "/dashboard/pos/")
    with page.expect_navigation(timeout=120000):
        page.evaluate("document.querySelector('form[action=\"/demo/reset/\"]').submit()")
    page.wait_for_load_state("load")


def as_role(page, role, path):
    page.goto(f"{BASE}/dashboard/demo/enter/?as={role}")
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")


def screenshots(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
    page = ctx.new_page()
    reset(page)
    page.goto(f"{BASE}/demo/site/?lang=en")
    page.wait_for_load_state("networkidle")
    shot(page, "site-home")
    page.goto(f"{BASE}/demo/site/menu/")
    shot(page, "site-menu")
    page.goto(f"{BASE}/demo/site/reservations/")
    shot(page, "site-booking", wait=2)

    as_role(page, "waiter", "/dashboard/pos/")
    shot(page, "waiter-floor")
    table(page, 4)
    page.click("text=Food")
    page.click(".cat-tile:has-text('Main Course')")
    page.click(".cat-tile:has-text('Meat')")
    shot(page, "waiter-order")
    page.click(".prod-tile:has-text('Smoked brisket')")
    page.click(".opt-choices label:has-text('Fatty')")
    page.click(".opt-choices label:has-text('Mac & cheese')")
    shot(page, "waiter-options", wait=0.6)
    page.keyboard.press("Escape")

    as_role(page, "chef", "/dashboard/pos/kitchen/")
    shot(page, "kitchen")
    as_role(page, "bartender", "/dashboard/pos/bar/")
    shot(page, "bar")
    as_role(page, "manager", "/dashboard/pos/overview/")
    shot(page, "overview")
    page.goto(f"{BASE}/dashboard/pos/cassa/")
    page.click(".cassa-list a.billing")
    page.wait_for_load_state("networkidle")
    shot(page, "cassa")
    page.goto(f"{BASE}/dashboard/pos/floor/")
    shot(page, "floor")
    page.goto(f"{BASE}/dashboard/pos/floor/design/")
    shot(page, "floor-design")
    page.goto(f"{BASE}/dashboard/pos/reservations/?period=week")
    shot(page, "reservations")
    page.goto(f"{BASE}/dashboard/pos/performance/?period=month")
    shot(page, "performance")
    as_role(page, "owner", "/dashboard/finance/?period=month")
    shot(page, "finance")
    page.goto(f"{BASE}/app/?source=switch&lang=en")
    shot(page, "app-start")
    page.goto(f"{BASE}/dashboard/home/")
    shot(page, "owner-home")
    ctx.close()


SCENES = [
    ("site-home", "Your own restaurant website", "Built in with a drag & drop builder: menu, reviews, map and online booking."),
    ("site-booking", "Online reservations", "Guests pick a date and a free 30-minute slot. The table is reserved at once."),
    ("waiter-floor", "Live floor for the waiter", "Every table shows its status: free, reserved, occupied, ready to serve or bill requested."),
    ("waiter-options", "Order per guest", "Guest #1, Guest #2 … with options like doneness and side, and notes for the kitchen."),
    ("kitchen", "Kitchen display", "Food goes straight to the chef: oldest first, with timers. Late tickets turn red."),
    ("bar", "Bar queue", "Drinks go to the bartender. One tap marks them completed and the waiter is told."),
    ("overview", "Live overview", "Managers see every open table, the bar and kitchen load and today's sales."),
    ("cassa", "Cassa", "Split the bill per guest, add a tip, cash or card, and print a PDF bill."),
    ("floor-design", "Floor designer", "Drag tables and sections. Round or rectangle, for every room and terrace."),
    ("reservations", "Reservations", "Day, week or month. Every reservation opens the full customer profile."),
    ("finance", "Finance", "Profit & Loss, OB (sales tax) and PDF reports — made for Curaçao."),
    ("owner-home", "One system for everyone", "Waiters, bartenders, chefs, managers and owners — in English, Dutch and Spanish."),
]

VIDEO_PAGE = """<!doctype html><html><body style="margin:0;background:#000">
<canvas id="c" width="1280" height="720"></canvas>
<script>
const SCENES = %SCENES%;
const c = document.getElementById("c"), g = c.getContext("2d");
const load = (src) => new Promise((ok) => { const i = new Image(); i.onload = () => ok(i); i.src = src; });
const logo = new Image(); logo.src = "/static/odg/img/odg-restaurant.svg";
function title(t1, t2, a) {
  g.fillStyle = "#071d5a"; g.fillRect(0, 0, 1280, 720);
  const grd = g.createRadialGradient(200, 0, 50, 300, 100, 900); grd.addColorStop(0, "#1d47b8"); grd.addColorStop(1, "rgba(7,29,90,0)");
  g.fillStyle = grd; g.fillRect(0, 0, 1280, 720);
  g.globalAlpha = a; if (logo.complete) g.drawImage(logo, 590, 170, 100, 100);
  g.fillStyle = "#fff"; g.textAlign = "center"; g.font = "700 58px Segoe UI, sans-serif"; g.fillText(t1, 640, 360);
  g.fillStyle = "#ffc800"; g.font = "600 28px Segoe UI, sans-serif"; g.fillText(t2, 640, 415); g.globalAlpha = 1;
}
function scene(img, t, dur, cap, sub) {
  const p = t / dur, z = 1.0 + 0.06 * p;
  const w = 1280 * z, h = 800 * z;  // screenshots are 1440x900 (16:10)
  g.fillStyle = "#0d1530"; g.fillRect(0, 0, 1280, 720);
  g.drawImage(img, (1280 - w) / 2 - 20 * p, (720 - h) / 2 - 30 * p, w, h);
  const a = Math.min(1, t / 400, (dur - t) / 400);
  g.globalAlpha = Math.max(0, a);
  g.fillStyle = "rgba(7,16,45,.88)"; g.fillRect(0, 590, 1280, 130);
  g.fillStyle = "#ffc800"; g.fillRect(0, 590, 8, 130);
  g.textAlign = "left"; g.fillStyle = "#fff"; g.font = "700 34px Segoe UI, sans-serif"; g.fillText(cap, 48, 642);
  g.fillStyle = "#cfd8f6"; g.font = "400 23px Segoe UI, sans-serif"; g.fillText(sub, 48, 684);
  g.globalAlpha = 1;
}
window.makeVideo = async function () {
  const imgs = await Promise.all(SCENES.map((s) => load("/static/odg/img/screens/" + s[0] + ".jpg")));
  const stream = c.captureStream(30);
  const rec = new MediaRecorder(stream, { mimeType: "video/webm;codecs=vp9", videoBitsPerSecond: 750000 });
  const parts = []; rec.ondataavailable = (e) => e.data.size && parts.push(e.data);
  const done = new Promise((ok) => rec.onstop = ok);
  rec.start(500);
  const plan = [["title", 3200, "ODG-RESTAURANT", "The restaurant system for Curaçao"]]
    .concat(SCENES.map((s, i) => ["scene", 5600, i]))
    .concat([["title", 4200, "Try it yourself", "restaurant.oliverdeangroup.com/demo"]]);
  for (const step of plan) {
    const start = performance.now();
    await new Promise((ok) => {
      function frame() {
        const t = performance.now() - start;
        if (step[0] === "title") title(step[2], step[3], Math.min(1, t / 600, (step[1] - t) / 500));
        else scene(imgs[step[2]], t, step[1], SCENES[step[2]][1], SCENES[step[2]][2]);
        if (t < step[1]) requestAnimationFrame(frame); else ok();
      }
      frame();
    });
  }
  rec.stop(); await done;
  const blob = new Blob(parts, { type: "video/webm" });
  const buf = new Uint8Array(await blob.arrayBuffer());
  let bin = ""; for (let i = 0; i < buf.length; i += 32768) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 32768));
  return btoa(bin);
};
</script></body></html>"""


def video(browser):
    """Makes demo-tour.webm from the screenshots, recorded by the browser itself (no ffmpeg needed)."""
    import base64
    import json

    page = browser.new_page(viewport={"width": 1280, "height": 720})
    page.goto(f"{BASE}/robots.txt")  # same origin as the screenshots, so the canvas may be recorded
    page.evaluate("html => { document.open(); document.write(html); document.close(); }",
                  VIDEO_PAGE.replace("%SCENES%", json.dumps(SCENES)))
    page.wait_for_function("typeof window.makeVideo === 'function'")
    data = page.evaluate("window.makeVideo()", )
    VIDEO.mkdir(parents=True, exist_ok=True)
    out = VIDEO / "demo-tour.webm"
    out.write_bytes(base64.b64decode(data))
    page.evaluate("title('ODG-RESTAURANT', 'The restaurant system for Curaçao', 1)")  # the opening card as poster
    page.screenshot(path=str(SHOTS / "video-poster.jpg"), type="jpeg", quality=80)
    print("saved video", out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        if "--video-only" not in sys.argv:
            screenshots(browser)
        if "--no-video" not in sys.argv:
            video(browser)
        browser.close()
