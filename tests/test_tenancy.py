"""Tenants and events (issue #466): where each one's documents live. See docs/tenancy.md."""
import json

import pytest

from floorbit import database, store, tenancy


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.delenv(database.ENV, raising=False)
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))
    tenancy.forget()
    yield tmp_path
    tenancy.forget()


def _events(tmp_path, events):
    (tmp_path / "tenant.json").write_text(json.dumps({"events": events}))
    tenancy.forget()


def test_without_tenant_json_everything_stays_where_it_was(state):
    assert tenancy.events() == [{"id": "main", "name": "", "status": "live", "folder": ""}]
    assert store.event_file() == store.DATA_FILE
    assert store.tenant_file() == store.DATA_FILE
    assert store.event_path("halls") == str(state / "halls")
    assert store.tenant_path("plugins.json") == str(state / "plugins.json")
    # A file someone configured (CHECKIN_FILE and so on) is left exactly as it was.
    assert store.event_file("/elsewhere/checkins.json") == "/elsewhere/checkins.json"


def test_a_later_live_event_gets_its_own_folder(state):
    store.save_data({"seat_blocks": [{"id": "A"}], "auth_users": {"mike": {}}})
    _events(state, [{"id": "main", "status": "closed"}, {"id": "lan-2027", "status": "live", "name": "LAN 2027"}])
    assert tenancy.live()["folder"] == "event-data/lan-2027"
    assert store.event_path("halls") == str(state / "event-data" / "lan-2027" / "halls")
    assert store.event_file("/elsewhere/checkins.json") == str(state / "event-data" / "lan-2027" / "checkins.json")
    # Tenant documents stay in the tenant's folder.
    assert store.tenant_file() == store.DATA_FILE
    assert store.tenant_path("plugins.json") == str(state / "plugins.json")

    assert store.load_data()["seat_blocks"] == []      # the new event starts empty
    store.save_data({"seat_blocks": [{"id": "B"}]})
    assert json.loads((state / "event-data" / "lan-2027" / "data.json").read_text()) == {"seat_blocks": [{"id": "B"}]}
    # The first event's plan (and the accounts beside it) are untouched.
    assert json.loads((state / "data.json").read_text())["seat_blocks"] == [{"id": "A"}]


def test_using_picks_an_event_for_a_block(state):
    store.save_data({"seat_blocks": [{"id": "A"}]})
    _events(state, [{"id": "main", "status": "planning"}, {"id": "next", "status": "live"}])
    with tenancy.using_event(tenancy.find("main")):
        assert store.load_data()["seat_blocks"] == [{"id": "A"}]
    assert store.load_data()["seat_blocks"] == []


def test_the_event_list_is_made_safe(state):
    _events(state, [
        {"id": "main", "status": "live"},
        {"id": "../../etc", "status": "live"},          # becomes a folder name: refused
        {"id": "b", "status": "live", "folder": "/tmp"},  # the folder comes from the id, never the file
        {"id": "b", "status": "planning"},               # a second "b": dropped
        {"id": "c", "status": "whatever"},
        "not an event",
    ])
    assert [(e["id"], e["status"], e["folder"]) for e in tenancy.events()] == [
        ("main", "live", ""), ("b", "planning", "event-data/b"), ("c", "planning", "event-data/c")]


def test_no_live_event_means_the_first_one(state):
    _events(state, [{"id": "a", "status": "closed"}, {"id": "b", "status": "planning"}])
    assert tenancy.live()["id"] == "a"


def test_a_broken_tenant_json_falls_back_to_the_default(state):
    (state / "tenant.json").write_text("[1, 2]")
    tenancy.forget()
    assert tenancy.live()["id"] == "main"


def test_events_in_a_database_are_kept_apart(state, monkeypatch):
    monkeypatch.setenv(database.ENV, f"sqlite:///{state / 'floorbit.db'}")
    try:
        store.save_data({"seat_blocks": [{"id": "A"}]})
        store.write_json(store.tenant_path(tenancy.TENANT_FILE),
                         {"events": [{"id": "main", "status": "planning"}, {"id": "x", "status": "live"}]})
        tenancy.forget()
        store.save_data({"seat_blocks": [{"id": "X"}]})
        db = database.backend()
        assert json.loads(db.get_text("event-data/x/data.json")) == {"seat_blocks": [{"id": "X"}]}
        assert json.loads(db.get_text("data.json")) == {"seat_blocks": [{"id": "A"}]}
    finally:
        database.backend().close()


def test_accounts_and_settings_read_the_tenant_file(state):
    from auth.users import UserStore
    from floorbit.settings import SettingsStore
    store.write_json(store.DATA_FILE, {"auth_users": {"mike": {"username": "mike"}}, "app_settings": {}})
    _events(state, [{"id": "main", "status": "closed"}, {"id": "next", "status": "live"}])
    # Built the way create_app builds them: they follow the tenant, not the live event.
    users = UserStore(store.tenant_file)
    assert users.path == store.DATA_FILE and "mike" in users._users()
    assert SettingsStore(store.tenant_file, environ={}).data_file == store.DATA_FILE
