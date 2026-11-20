"""Screenshots of the running app for merge requests: desktop and phone, every page.

    python scripts/screenshots.py [out-dir]        # APP_URL defaults to http://127.0.0.1:5000

The `screenshots` CI job starts the app with an empty data file, a demo account
(AUTH_ADMIN_USER / AUTH_ADMIN_PASSWORD) and FLOORBIT_DEMO=1, so the demo plugin has already laid
out a made-up hall with players and traffic. This script signs in and takes the pictures, the
sign-in page included. Without demo mode it places a few example switches, seat blocks and seat
entries itself (example names and documentation IPs only).
"""

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("APP_URL", "http://127.0.0.1:5000").rstrip("/")
PAGES = {"floorplan": "/", "settings": "/settings", "kiosk": "/dashboards/kiosk"}
DEMO_SWITCHES = [
    {"name": "sw-demo-01", "x": 25, "y": 30},
    {"name": "sw-demo-02", "x": 60, "y": 30},
]
DEMO_BLOCKS = [
    {"name": "A", "x": 15, "y": 45, "cols": 10, "rows": 2},
    {"name": "B", "x": 50, "y": 45, "cols": 10, "rows": 2},
]
# Example values only (RFC 5737 addresses, made-up nicks): screenshots never show real people.
DEMO_SEATS = {
    "A-1": {"ip": "192.0.2.11", "mac": "02:00:00:00:00:11", "nick": "player-one"},
    "A-2": {"ip": "192.0.2.12", "nick": "player-two", "note": "Brought a second PC"},
    "B-1": {"mac": "02:00:00:00:00:21", "nick": "player-three"},
}

# Signs in with this account first (see the module docstring).
USER = os.environ.get("SCREENSHOT_USER") or os.environ.get("AUTH_ADMIN_USER", "")
PASSWORD = os.environ.get("SCREENSHOT_PASSWORD") or os.environ.get("AUTH_ADMIN_PASSWORD", "")
PAGES["users"] = "/settings/users"
PAGES["plugins"] = "/settings/plugins"
PAGES["widgets"] = "/widgets"
PAGES["network"] = "/dashboards/network"
PAGES["traffic"] = "/dashboards/traffic"
PAGES["inventory"] = "/inventory"
PAGES["seat-mapping"] = "/seat-mapping"
PAGES["teams"] = "/settings/teams"
PAGES["sign-in"] = "/settings/sign-in"
PAGES["incidents"] = "/incidents"
PAGES["health"] = "/dashboards/health"
PAGES["security"] = "/security"
PAGES["power"] = "/power"
PAGES["problems"] = "/problems"
PAGES["s3-backups"] = "/settings/backup"
PAGES["tile-levels"] = "/dashboards/tile-levels"
PAGES["tile-charts"] = "/dashboards/tile-charts"
PAGES["tile-data"] = "/dashboards/tile-data"


def tile(name, x, y, w, h, **look):
    return {"x": x, "y": y, "w": w, "h": h, "node": {"pane": {"kind": "tile", "tile": f"floorbit/w/{name}", **look}}}


# One tile at every level (issue #924): the same data small, medium and large.
TILE_LEVELS = {"name": "Tile levels", "fit": True, "sections": [{"panels": [
    tile("switches", 0, 0, 4, 3), tile("switch_states", 4, 0, 4, 3), tile("open_incidents", 8, 0, 4, 3),
    tile("traffic", 12, 0, 6, 3), tile("seats", 18, 0, 6, 3),
    tile("switch_states", 0, 3, 8, 6), tile("traffic", 8, 3, 16, 6),
    tile("open_incidents", 0, 9, 12, 7), tile("switch_states", 12, 9, 12, 7, type="table", level="l"),
]}]}
# The same data as a gauge, a pie, horizontal and vertical bars.
TILE_CHARTS = {"name": "Tile charts", "fit": True, "sections": [{"panels": [
    tile("seats", 0, 0, 6, 8, type="gauge"), tile("switch_states", 6, 0, 8, 8, type="pie"),
    tile("seats_by_block", 14, 0, 10, 8, type="bar"),
    tile("seats_by_block", 0, 8, 8, 8, type="column"), tile("traffic", 8, 8, 16, 8, type="column"),
    tile("traffic", 0, 16, 12, 8, stack="stacked", style="area", trend="average"),
    tile("traffic", 12, 16, 6, 8, type="histogram"), tile("traffic", 18, 16, 6, 8, type="column", stack="percent"),
]}]}
# Several sources, grouping and calculations (issue #959).
TILE_DATA = {"name": "Tile data", "fit": True, "sections": [{"panels": [
    tile("seats", 0, 0, 8, 8, also=["floorbit/w/switches"], type="bar", title="Seats and switches"),
    tile("switch_states", 8, 0, 8, 8, group_by="state", type="column", title="Switches by state"),
    tile("traffic", 16, 0, 8, 8, reduce="avg", type="bar", title="Average traffic"),
    tile("traffic", 0, 8, 16, 8, legend=["min", "avg", "max"], title="Traffic, min, average and max"),
    tile("traffic", 16, 8, 8, 8, reduce="max", title="Peak traffic"),
    # Numbers and colours (issue #960): steps by share of the max, top 3, a step line on a graph.
    tile("seats_by_block", 0, 16, 8, 8, type="bar", sort="value-asc", limit=3, threshold_mode="percent",
         thresholds=[{"at": 0, "tone": "err"}, {"at": 70, "tone": "warn"}, {"at": 85, "tone": "ok"}],
         title="Emptiest blocks"),
    tile("seats", 8, 16, 8, 8, type="gauge", threshold_mode="percent",
         thresholds=[{"at": 50, "tone": "warn"}, {"at": 90, "tone": "ok"}]),
    tile("traffic", 16, 16, 8, 8, short=True, decimals=1, thresholds=[{"at": 4e9, "tone": "warn"}],
         title="Traffic over 4 Gbit/s"),
]}]}
SEEDED = {"tile-levels": TILE_LEVELS, "tile-charts": TILE_CHARTS, "tile-data": TILE_DATA}

opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read() or b"null")


def sign_in():
    if not USER:
        return
    form = urllib.parse.urlencode({"username": USER, "password": PASSWORD}).encode()
    try:
        opener.open(urllib.request.Request(BASE + "/login", data=form, method="POST"), timeout=10)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Signing in as {USER} failed: HTTP {exc.code}")


def wait_for_app(seconds=60):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            call("GET", "/api/config")
            return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(1)
    sys.exit(f"{BASE} did not answer within {seconds} s")


def seed():
    # Only on an empty floor plan, so a local run never touches real data.
    if call("GET", "/api/switches")[1] or call("GET", "/api/seat-blocks")[1]:
        return
    for switch in DEMO_SWITCHES:
        call("POST", "/api/switches", switch)
    for block in DEMO_BLOCKS:
        call("POST", "/api/seat-blocks", block)
    for seat, entry in DEMO_SEATS.items():
        call("PUT", f"/api/seat-map/{seat}", entry)


def seed_tile_levels():
    for name, board in SEEDED.items():
        try:
            call("GET", f"/api/dashboards/{name}")
        except urllib.error.HTTPError:
            try:
                call("PUT", f"/api/dashboards/{name}", board)
            except urllib.error.HTTPError as exc:
                print(f"Could not save the {name} dashboard: HTTP {exc.code}", file=sys.stderr)


def page_exists(path):
    try:
        return call("GET", path)[0] == 200
    except urllib.error.HTTPError:
        return False
    except json.JSONDecodeError:
        return True  # an HTML page


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
    out.mkdir(parents=True, exist_ok=True)
    wait_for_app()
    sign_in()
    seed()
    seed_tile_levels()
    pages = {name: path for name, path in PAGES.items() if page_exists(path)}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        views = {
            "desktop": {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 2},
            "phone": pw.devices["iPhone 13"],
        }
        for view, options in views.items():
            context = browser.new_context(**options, color_scheme="dark")
            page = context.new_page()
            page.goto(BASE + "/login", wait_until="networkidle")
            if page.url.split("?")[0].endswith("/login"):
                target = out / f"login-{view}.png"
                page.screenshot(path=str(target))
                print(target)
                if USER:
                    page.fill("input[name=username]", USER)
                    page.fill("input[name=password]", PASSWORD)
                    page.click("button[type=submit]")
                    # Signing in lands on the editor, whose live-updates stream never goes idle.
                    page.wait_for_load_state("load")
            for name, path in pages.items():
                # "load", not "networkidle": the live-updates stream (/api/events) never goes idle.
                page.goto(BASE + path, wait_until="load")
                page.wait_for_timeout(1500)  # let the first fetches finish and the canvas settle
                target = out / f"{name}-{view}.png"
                page.screenshot(path=str(target))
                print(target)
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
