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
