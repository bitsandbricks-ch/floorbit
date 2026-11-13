"""Screenshots of the running app for merge requests: desktop and phone, every page.

    python scripts/screenshots.py [out-dir]        # APP_URL defaults to http://127.0.0.1:5000

The `screenshots` CI job starts the app with an empty data file, and this script places a few
demo switches and seat blocks (example names only) before it takes the pictures.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("APP_URL", "http://127.0.0.1:5000").rstrip("/")
PAGES = {"floorplan": "/", "settings": "/settings"}
DEMO_SWITCHES = [
    {"name": "sw-demo-01", "x": 25, "y": 30},
    {"name": "sw-demo-02", "x": 60, "y": 30},
]
DEMO_BLOCKS = [
    {"name": "A", "x": 15, "y": 45, "cols": 10, "rows": 2},
    {"name": "B", "x": 50, "y": 45, "cols": 10, "rows": 2},
]


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read() or b"null")


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
            for name, path in pages.items():
                page.goto(BASE + path, wait_until="networkidle")
                page.wait_for_timeout(500)  # let the canvas settle after the last fetch
                target = out / f"{name}-{view}.png"
                page.screenshot(path=str(target))
                print(target)
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
