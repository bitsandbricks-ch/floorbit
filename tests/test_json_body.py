"""A JSON body that isn't an object is refused before a handler reads it (floorbit/json_body.py).
Handlers do ``body = request.get_json(silent=True) or {}`` and then ``body.get(...)``; a body
like "x", 5 or [1] used to answer 500 on about 40 write endpoints."""
import json

import pytest

WRITES = [("post", "/api/cables"), ("post", "/api/halls"), ("post", "/api/teams"), ("put", "/api/notice"),
          ("post", "/api/seat-blocks"), ("post", "/api/users")]


@pytest.mark.parametrize("body", ["x", 5, True, [1], [{"a": 1}]])
@pytest.mark.parametrize(("method", "path"), WRITES)
def test_a_body_that_is_not_an_object_gets_400_not_500(client, method, path, body):
    r = getattr(client, method)(path, json=body)
    assert r.status_code == 400 and r.get_json()["error"] == "Send a JSON object."


def test_the_refusal_speaks_german(client):
    r = client.post("/api/halls", json=[1], headers={"Accept-Language": "de-CH"})
    assert r.get_json()["error"] == "Sende ein JSON-Objekt."


def test_objects_empty_bodies_and_forms_still_get_through(client):
    assert client.post("/api/teams", json={"name": "Network"}).status_code == 201
    assert client.post("/api/halls", data="", content_type="application/json").status_code != 500
    # Not JSON at all: the guard leaves it to the handler.
    assert client.post("/api/halls", data={"name": "x"}).status_code != 500


def test_wrong_types_inside_an_object(client):
    assert client.post("/api/teams", json={"name": {"a": 1}}).status_code == 400
    assert client.post("/api/teams", json={"name": "Desk", "parent": ["x"]}).status_code == 400


def test_signed_out_still_gets_401_first(anon_client):
    assert anon_client.post("/api/halls", json=[1]).status_code in (401, 403)


@pytest.mark.parametrize("field", ["username", "password", "role", "display_name"])
@pytest.mark.parametrize("value", [{"a": 1}, [1], 5, ["x"] * 20])
def test_an_account_field_of_the_wrong_type_is_a_400(client, field, value):
    body = {"username": "kim", "password": "a-long-example-pw", "role": "viewer", field: value}
    r = client.post("/api/users", json=body)
    # A display name that isn't text is ignored; everything else is refused.
    assert r.status_code == (201 if field == "display_name" else 400), r.get_json()
    if field == "display_name":
        assert client.patch("/api/users/kim", json={"display_name": value}).status_code == 200


@pytest.mark.parametrize("value", [{"a": 1}, [1], 5])
def test_an_api_token_role_of_the_wrong_type_is_a_400(client, value):
    assert client.post("/api/settings/api-tokens", json={"name": "Bot", "role": value}).status_code == 400


def test_a_body_nested_too_deep_gets_400_not_500(client, anon_client):
    # A megabyte of "[" made the parser itself run out of stack (RecursionError: a 500, a traceback
    # in the log per request), signed in or not.
    for c in (client, anon_client):
        r = c.post("/api/seat-blocks", data="[" * 200000 + "]" * 200000, content_type="application/json")
        assert r.status_code in (400, 401, 403)
    r = client.post("/api/teams", data='{"a":' * 50000 + "1" + "}" * 50000, content_type="application/json")
    assert r.status_code == 400 and r.get_json()["error"] == "The JSON is nested too deeply."
    # Deep enough to parse but past the limit: saved, it could break every later save of the document.
    deep = {"name": "Network"}
    for _ in range(100):
        deep = {"x": deep}
    assert client.post("/api/teams", json={"name": "Desk", "extra": deep}).status_code == 400
    r = client.post("/api/teams", json={"name": "Desk", "extra": deep}, headers={"Accept-Language": "de-CH"})
    assert r.get_json()["error"] == "Das JSON ist zu tief verschachtelt."


def test_ordinary_nesting_still_gets_through(client):
    from floorbit.json_body import too_deep
    nested = {"a": [{"b": [{"c": 1}]}]}
    assert not too_deep(nested) and not too_deep(None) and not too_deep("x")
    assert client.post("/api/teams", json={"name": "Network", "extra": nested}).status_code == 201


def test_a_delete_with_a_deep_body_gets_400_and_others_keep_their_shape(client):
    """DELETE bodies were not checked: the audit log read a deep one after the handler, a 500."""
    r = client.delete("/api/notice", data='{"a":' * 50000 + "1" + "}" * 50000, content_type="application/json")
    assert r.status_code == 400 and r.get_json()["error"] == "The JSON is nested too deeply."
    assert client.delete("/api/notice", json=[1, 2]).status_code < 500       # no new shape rule for DELETE
    assert client.delete("/api/notice").status_code < 500


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e999"])
@pytest.mark.parametrize(("method", "path", "body"), [
    ("post", "/api/seat-blocks/many", '{"hall_id": "main", "count": %s}'),
    ("patch", "/api/alerts/mutes/sw-1", '{"minutes": %s}'),
    ("post", "/api/links", '{"a": "sw-1", "b": "sw-2", "speed": %s}'),
    ("post", "/api/halls", '{"name": "Hall", "background_opacity": [1, {"deep": %s}]}'),
])
def test_nan_and_infinity_get_400_not_500(client, method, path, body, number):
    """Python's parser takes NaN, Infinity and 1e999, and int() of them raised OverflowError (a 500)."""
    r = client.open(path, method=method, data=body % number, content_type="application/json")
    assert r.status_code == 400 and r.get_json()["error"] == "Numbers must be finite (no NaN or Infinity)."
    r = client.open(path, method=method, data=body % number, content_type="application/json",
                    headers={"Accept-Language": "de-CH"})
    assert r.get_json()["error"].startswith("Zahlen müssen endlich sein")


def test_ordinary_numbers_and_the_agent_link_are_left_alone(client):
    assert client.post("/api/teams", data='{"name": "Network", "order": 1.5e3}',
                       content_type="application/json").status_code == 201
    # The agent's calls carry what devices said; its own handlers judge them (no 400 from the guard).
    r = client.post("/api/agent/v1/report", data='{"value": NaN}', content_type="application/json")
    assert r.get_json(silent=True) is None or "finite" not in r.get_json().get("error", "")


@pytest.mark.parametrize("text", ["nan", "inf", "-Infinity"])
def test_nan_as_text_never_lands_on_the_plan(client, text):
    """float() reads the text "nan" too, which the body guard can't see. A switch or patch panel
    saved at x=NaN made /api/plan and /api/switches answer a bare NaN, which no browser parses."""
    switch = {"name": "sw-nan", "x": text, "y": 10}
    assert client.post("/api/inventory", json=switch).status_code == 400
    made = client.post("/api/inventory", json={"name": "sw-ok", "x": 5, "y": 5})
    assert made.status_code in (200, 201)
    assert client.patch(f"/api/inventory/{made.get_json()['id']}", json={"x": text, "y": 1}).status_code == 400
    assert client.post("/api/cable-plan/panels", json={"name": "PP-1", "x": 1, "y": text}).status_code == 400
    for path in ("/api/plan", "/api/switches", "/api/inventory", "/api/cable-plan"):
        json.loads(client.get(path).get_data(as_text=True), parse_constant=_refuse)


def _refuse(constant):
    raise AssertionError(f"{constant} in an answer")


@pytest.mark.parametrize("since", ["nan", "inf", "-inf", "1e999"])
def test_a_cable_walk_since_nan_still_answers_json_a_browser_reads(client, since):
    r = client.get(f"/api/cables/walk?switch=sw-1&since={since}")
    assert r.status_code == 200
    json.loads(r.get_data(as_text=True), parse_constant=_refuse)


def test_a_nan_saved_before_the_checks_goes_out_as_null(client):
    """A position saved as NaN by an older version broke /api/plan for everyone (JSON.parse
    refuses a bare NaN). Answers now carry null there, so the page loads and the switch can be moved."""
    from floorbit import store
    made = client.post("/api/inventory", json={"name": "sw-old", "x": 5, "y": 5}).get_json()
    data = store.load_data()
    for dev in data["inventory"]:
        if dev.get("id") == made["id"]:
            dev["x"], dev["y"] = float("nan"), float("inf")
    store.save_data(data)
    for path in ("/api/plan", "/api/switches", "/api/inventory"):
        body = json.loads(client.get(path).get_data(as_text=True), parse_constant=_refuse)
        assert "sw-old" in json.dumps(body)
    dev = next(d for d in client.get("/api/inventory").get_json()["devices"] if d.get("id") == made["id"])
    assert dev["x"] is None and dev["y"] is None


def test_a_live_event_with_nan_reaches_the_page_as_readable_json():
    from integrations import events
    line = events._format({"id": "1", "type": "status", "data": {"util": float("nan"), "ok": 1.5}})
    payload = line.split("data: ", 1)[1].strip()
    assert json.loads(payload, parse_constant=_refuse)["data"] == {"util": None, "ok": 1.5}


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e999"])
@pytest.mark.parametrize(("method", "path"), [("post", "/api/seat-blocks"), ("post", "/api/cables"),
                                              ("put", "/api/settings")])
def test_nan_and_infinity_are_refused_before_a_handler_reads_them(client, method, path, number):
    # Python's JSON reader takes these; as a whole number they raised OverflowError (a 500).
    r = getattr(client, method)(path, data=f'{{"x": 1, "y": 1, "cache.ttl_arp": {number}}}',
                                content_type="application/json")
    assert r.status_code == 400 and "finite" in r.get_json()["error"]



@pytest.mark.parametrize("number", ["1" + "0" * 400, "-" + "9" * 31])
def test_whole_numbers_of_hundreds_of_digits_are_refused(client, number):
    # float() of one raised OverflowError (a 500), as on a power reading typed in by hand.
    r = client.post("/api/seat-blocks", data=f'{{"x": 1, "y": {number}}}', content_type="application/json")
    assert r.status_code == 400 and "30 digits" in r.get_json()["error"]
    assert client.post("/api/teams", json={"name": "Big", "order": 10 ** 29}).status_code == 201

def test_ordinary_numbers_still_get_through(client):
    assert client.post("/api/teams", json={"name": "Network", "order": 1.5e3}).status_code == 201


def test_answers_never_hold_nan_or_infinity(app_module):
    # A monitoring source's "NaN" (Prometheus, for a rate over nothing) made the whole answer unreadable.
    import json

    from flask import jsonify
    with app_module.app.test_request_context():
        body = jsonify({"rate": float("nan"), "series": [1.5, float("inf")], "nested": {"x": -float("inf")}}).data
    assert json.loads(body) == {"rate": None, "series": [1.5, None], "nested": {"x": None}}
    assert b"NaN" not in body and b"Infinity" not in body
