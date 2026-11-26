"""The LAN cache's numbers while a cache log comes in without the Marketplace plugin (issue #1420).
They show on Traffic > Games and downloads (#1642)."""
from datetime import UTC, datetime


def test_numbers_come_in_without_the_plugin(client, app_module):
    stats = app_module.app.extensions["floorbit_lancache"]
    now = datetime.now(UTC).strftime("%d/%b/%Y:%H:%M:%S +0000")
    stats.add_lines([f'[steam] 192.0.2.10 / - - - [{now}] "GET /depot/1/chunk/a" 200 1024 "-" '
                     '"Valve/Steam HTTP Client 1.0" "HIT" "lancache.steamcontent.com" "-"'])
    try:
        assert "/games" in [p["href"] for p in client.get("/api/pages").get_json()["pages"]]
        body = client.get("/api/lancache?hours=168").get_json()
        # The page hides "plugin not installed" once data comes in (it reads ``configured``).
        assert body["configured"] is True and body["plugin_installed"] is False
    finally:
        stats.hours.clear()
