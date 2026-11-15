"""Event schedule and countdown (issue #106)."""
import datetime as dt
import time
from zoneinfo import ZoneInfo

import pytest

from floorbit import schedule

ZURICH = ZoneInfo("Europe/Zurich")
T0 = 1_900_000_000   # 2030-03-17

ICS = """BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:open@example.com\r
DTSTART;TZID=Europe/Zurich:20300317T100000\r
DTEND;TZID=Europe/Zurich:20300317T103000\r
SUMMARY:Opening keynote\\, welcome\r
LOCATION:Main stage\r
DESCRIPTION:Doors open at 9.\\nBring your\r
  ticket.\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:cup@example.com\r
DTSTART:20300317T130000Z\r
DTEND:20300317T170000Z\r
SUMMARY:Rocket Cup finals\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:night@example.com\r
DTSTART:20300317T230000\r
DTEND:20300318T070000\r
SUMMARY:Nachtruhe\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:fest@example.com\r
DTSTART;VALUE=DATE:20300318\r
SUMMARY:Pizza day\r
CATEGORIES:Food\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:broken@example.com\r
DTSTART:yesterday\r
SUMMARY:Broken\r
END:VEVENT\r
END:VCALENDAR\r
"""


def _at(*parts):
    return dt.datetime(*parts, tzinfo=ZURICH).timestamp()


def test_parse_ics_reads_times_zones_folding_and_kinds():
    items = {i["uid"]: i for i in schedule.parse_ics(ICS, ZURICH)}
    assert set(items) == {"open@example.com", "cup@example.com", "night@example.com", "fest@example.com"}
    opening = items["open@example.com"]
    assert opening["title"] == "Opening keynote, welcome" and opening["kind"] == "talk"
    assert opening["start"] == _at(2030, 3, 17, 10) and opening["end"] == _at(2030, 3, 17, 10, 30)
    assert opening["where"] == "Main stage" and opening["note"] == "Doors open at 9. Bring your ticket."
    cup = items["cup@example.com"]
    assert cup["start"] == _at(2030, 3, 17, 14) and cup["kind"] == "tournament"
    assert items["night@example.com"]["kind"] == "quiet" and items["night@example.com"]["start"] == _at(2030, 3, 17, 23)
    assert items["fest@example.com"]["kind"] == "meal"
    assert items["fest@example.com"]["end"] - items["fest@example.com"]["start"] == 86400


def test_import_replaces_its_own_items_and_keeps_hand_made_ones(client):
    hand = client.post("/api/schedule/items", json={"title": "Group photo", "start": T0, "kind": "other"})
    assert hand.status_code == 201
    first = client.post("/api/schedule/import", json={"ics": ICS, "tz": "Europe/Zurich"}).get_json()
    assert first == {"added": 4, "updated": 0, "removed": 0}
    ids = {i["uid"]: i["id"] for i in client.get("/api/schedule").get_json()["items"] if i["uid"]}
    smaller = ICS.split("BEGIN:VEVENT\r\nUID:cup")[0] + "END:VCALENDAR\r\n"
    second = client.post("/api/schedule/import", json={"ics": smaller, "tz": "Europe/Zurich"}).get_json()
    assert second == {"added": 0, "updated": 1, "removed": 3}
    items = client.get("/api/schedule").get_json()["items"]
    assert [i["title"] for i in items] == ["Opening keynote, welcome", "Group photo"]
    assert items[0]["id"] == ids["open@example.com"]   # an update keeps the id


def test_import_refuses_what_isnt_a_calendar(client):
    assert client.post("/api/schedule/import", json={"ics": "hello"}).status_code == 400
    assert client.post("/api/schedule/import", json={"ics": ICS, "tz": "Mars/Base"}).status_code == 400
    empty = "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
    assert "no events" in client.post("/api/schedule/import", json={"ics": empty}).get_json()["error"]


def test_items_are_checked_and_edited(client):
    assert client.post("/api/schedule/items", json={"title": "", "start": T0}).status_code == 400
    assert client.post("/api/schedule/items", json={"title": "x", "start": T0, "end": T0 - 1}).status_code == 400
    assert client.post("/api/schedule/items", json={"title": "x", "start": 12}).status_code == 400
    assert client.post("/api/schedule/items", json={"title": "x", "start": T0, "kind": "party"}).status_code == 400
    item = client.post("/api/schedule/items", json={"title": "Lunch", "start": T0, "kind": "meal"}).get_json()
    changed = client.patch(f"/api/schedule/items/{item['id']}", json={"where": "Canteen"}).get_json()
    assert changed["where"] == "Canteen" and changed["title"] == "Lunch"
    assert client.delete(f"/api/schedule/items/{item['id']}").status_code == 200
    assert client.delete(f"/api/schedule/items/{item['id']}").status_code == 404


def test_viewers_read_leads_write(app_module):
    app_module.app.extensions["auth"].users.add("vic", "vic-password-1", role="viewer")
    viewer_client = app_module.app.test_client()
    assert viewer_client.post("/login", data={"username": "vic", "password": "vic-password-1"}).status_code == 302
    assert viewer_client.get("/api/schedule").status_code == 200
    assert viewer_client.post("/api/schedule/items", json={"title": "x", "start": T0}).status_code == 403
    assert viewer_client.put("/api/schedule/event", json={"start": T0}).status_code == 403


def test_public_now_next_and_countdown():
    now = T0
    items = [
        {"id": "a", "title": "Doors", "kind": "other", "start": now - 3600, "end": now - 1800},
        {"id": "b", "title": "Talk", "kind": "talk", "start": now - 600, "end": now + 600},
        {"id": "c", "title": "Night", "kind": "quiet", "start": now - 60, "end": now + 3600},
        {"id": "d", "title": "Final", "kind": "tournament", "start": now + 3600, "end": None},
    ]
    data = {"schedule": {"event": {"start": now + 90061, "end": None}, "items": items}}
    s = schedule.public(data, now=now)
    assert s["phase"] == "before" and s["countdown"] == 90061
    assert [i["id"] for i in s["now"]] == ["b", "c"] and s["quiet"]["id"] == "c"
    assert [i["id"] for i in s["next"]] == ["d"]
    data["schedule"]["event"] = {"start": now - 10, "end": now - 5}
    assert schedule.public(data, now=now)["phase"] == "after"


@pytest.fixture
def agenda_on(client):
    assert client.put("/api/settings", json={"public.schedule": True}).status_code == 200


def test_agenda_is_off_by_default(anon_client):
    assert anon_client.get("/agenda").status_code == 404
    assert anon_client.get("/agenda.json").status_code == 404


def test_agenda_page(client, anon_client, agenda_on):
    now = time.time()
    client.put("/api/schedule/event", json={"start": now + 2 * 86400 + 3 * 3600})
    client.post("/api/schedule/items", json={"title": "Opening", "kind": "talk", "start": now + 2 * 86400 + 3 * 3600,
                                             "where": "Main stage"})
    page = anon_client.get("/agenda").get_data(as_text=True)
    assert "The event starts in" in page and 'data-unit="d">2<' in page and "Opening" in page
    body = anon_client.get("/agenda.json").get_json()
    assert body["phase"] == "before" and body["next"][0]["title"] == "Opening"
    assert "by" not in body["items"][0] and "updated_at" not in body["items"][0]
    de = anon_client.get("/agenda?screen=1", headers={"Accept-Language": "de-CH,de"}).get_data(as_text=True)
    assert "Der Event beginnt in" in de and 'class="screen"' in de
