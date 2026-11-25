"""The LAN cache page while a cache log comes in without the Marketplace plugin (issue #1420)."""
from datetime import UTC, datetime


def _hrefs(client):
    return [p["href"] for p in client.get("/api/pages").get_json()["pages"]]


def test_page_listed_while_data_comes_in(client, app_module):
    stats = app_module.app.extensions["floorbit_lancache"]
    assert "/lancache" not in _hrefs(client)
    now = datetime.now(UTC).strftime("%d/%b/%Y:%H:%M:%S +0000")
    stats.add_lines([f'[steam] 192.0.2.10 / - - - [{now}] "GET /depot/1/chunk/a" 200 1024 "-" '
                     '"Valve/Steam HTTP Client 1.0" "HIT" "lancache.steamcontent.com" "-"'])
    try:
        assert "/lancache" in _hrefs(client)
        body = client.get("/api/lancache?hours=168").get_json()
        # The page hides "plugin not installed" once data comes in (it reads ``configured``).
        assert body["configured"] is True and body["plugin_installed"] is False
    finally:
        stats.hours.clear()
