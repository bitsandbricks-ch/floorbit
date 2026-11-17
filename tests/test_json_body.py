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
