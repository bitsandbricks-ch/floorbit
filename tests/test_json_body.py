"""A JSON body that isn't an object is refused before a handler reads it (floorbit/json_body.py).
Handlers do ``body = request.get_json(silent=True) or {}`` and then ``body.get(...)``; a body
like "x", 5 or [1] used to answer 500 on about 40 write endpoints."""
import pytest

WRITES = [("post", "/api/cables"), ("post", "/api/halls"), ("post", "/api/teams"), ("put", "/api/notice"),
          ("post", "/api/runbooks"), ("post", "/api/seat-blocks"), ("post", "/api/users")]


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


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e999"])
@pytest.mark.parametrize(("method", "path"), [("post", "/api/seat-blocks"), ("post", "/api/cables"),
                                              ("put", "/api/settings")])
def test_nan_and_infinity_are_refused_before_a_handler_reads_them(client, method, path, number):
    # Python's JSON reader takes these; as a whole number they raised OverflowError (a 500).
    r = getattr(client, method)(path, data=f'{{"x": 1, "y": 1, "cache.ttl_arp": {number}}}',
                                content_type="application/json")
    assert r.status_code == 400 and "finite" in r.get_json()["error"]


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
