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
PAGES = {"floorplan": "/", "settings": "/settings", "kiosk": "/kiosk"}
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
PAGES["dashboard"] = "/dashboard"
PAGES["inventory"] = "/inventory"
PAGES["seat-mapping"] = "/seat-mapping"
PAGES["teams"] = "/settings/teams"
PAGES["sign-in"] = "/settings/sign-in"

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
