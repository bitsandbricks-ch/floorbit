"""Agents sign every request with their own pinned key (floorbit/agent_identity.py, #1178)."""
import json
import time

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID

from floorbit import agent_identity, agent_link
from tests.agent_keys import UNSIGNED, agent_csr, agent_private_key, agent_signature
from tests.test_agent import clean_tunnel, enrol, head  # noqa: F401  # the fixture resets the tunnel

SIG = agent_identity.SIGNATURE_HEADER


def _id(key):
    return agent_link.KEY_RE.match(key).group(1)


def _signed(key, method, path, body=b"", private=None, stamp=None):
    return {**head(key), SIG: agent_signature(_id(key), method, path, body, key=private, stamp=stamp)}


def test_the_first_enrolment_pins_a_client_certificate(client, anon_client):
    made = enrol(client)
    res = anon_client.post("/api/agent/v1/identity", json={"csr": agent_csr(made["id"])},
                           headers={**head(made["key"]), UNSIGNED: "1"})
    assert res.status_code == 200, res.get_json()
    cert = x509.load_pem_x509_certificates(res.get_json()["cert"].encode())[0]
    assert cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value == x509.ExtendedKeyUsage(
        [ExtendedKeyUsageOID.CLIENT_AUTH])
    sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert sans.get_values_for_type(x509.UniformResourceIdentifier) == [f"urn:floorbit:agent:{made['id']}"]
    assert cert.public_key() == agent_private_key(made["id"]).public_key()
    page = client.get(f"/api/agents/{made['id']}/settings").get_json()
    assert page["identity"]["fingerprint"] == res.get_json()["fingerprint"]
    assert "public_key" not in json.dumps(page)


def test_a_second_key_cannot_take_the_pin_over(client, anon_client):
    made = enrol(client)
    assert anon_client.get("/api/agent/v1/hello", headers=head(made["key"])).status_code == 200   # enrols
    thief = ec.generate_private_key(ec.SECP256R1())
    # With the bearer key alone: not signed by the pinned key, refused.
    res = anon_client.post("/api/agent/v1/identity", json={"csr": agent_csr(made["id"], thief)},
                           headers={**head(made["key"]), UNSIGNED: "1"})
    assert res.status_code == 401
    # Signed by its own key: still not the pinned one.
    body = json.dumps({"csr": agent_csr(made["id"], thief)}).encode()
    res = anon_client.post("/api/agent/v1/identity", data=body, content_type="application/json",
                           headers=_signed(made["key"], "POST", "/api/agent/v1/identity", body, private=thief))
    assert res.status_code == 401
    mine = agent_identity.spki_of(agent_private_key(made["id"]).public_key())
    assert agent_identity.pinned(made["id"])["spki"] == mine


def test_the_agent_can_change_its_key_signed_with_the_old_one(client, anon_client):
    made = enrol(client)
    anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
    new = ec.generate_private_key(ec.SECP256R1())
    body = json.dumps({"csr": agent_csr(made["id"], new)}).encode()
    res = anon_client.post("/api/agent/v1/identity", data=body, content_type="application/json",
                           headers=_signed(made["key"], "POST", "/api/agent/v1/identity", body))
    assert res.status_code == 200
    assert agent_identity.pinned(made["id"])["spki"] == agent_identity.spki_of(new.public_key())


def test_the_bearer_key_alone_gets_nowhere(client, anon_client):
    made = enrol(client)
    anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
    for path in ("/api/agent/v1/calls?wait=0", "/api/agent/v1/plugins", "/api/agent/v1/seats"):
        res = anon_client.get(path, headers={**head(made["key"]), UNSIGNED: "1"})
        assert res.status_code == 401 and res.get_json()["code"] == "unsigned", path
    res = anon_client.post("/api/agent/v1/answers", json={"answers": []}, headers={**head(made["key"]), UNSIGNED: "1"})
    assert res.status_code == 401
    # Unsigned hello still answers (so an agent can learn the time), but it doesn't count as connected.
    hello = anon_client.get("/api/agent/v1/hello", headers={**head(made["key"]), UNSIGNED: "1"}).get_json()
    assert hello["identity"] == {**hello["identity"], "pinned": True, "signed": False}
    agent_link.tunnel.reset()
    anon_client.get("/api/agent/v1/hello", headers={**head(made["key"]), UNSIGNED: "1"})
    assert not agent_link.tunnel.connected(agent=made["id"])


def test_before_enrolling_only_hello_and_the_enrolment_answer(client, anon_client):
    made = enrol(client)
    unsigned = {**head(made["key"]), UNSIGNED: "1"}
    res = anon_client.get("/api/agent/v1/calls?wait=0", headers=unsigned)
    assert res.status_code == 401 and res.get_json()["code"] == "enrol"
    hello = anon_client.get("/api/agent/v1/hello", headers=unsigned).get_json()
    assert hello["identity"]["pinned"] is False and hello["identity"]["path"] == "/api/agent/v1/identity"


def test_a_signature_is_bound_to_path_body_and_time(client, anon_client):
    made = enrol(client)
    anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
    body = json.dumps({"answers": []}).encode()
    # Signed for another path.
    res = anon_client.post("/api/agent/v1/answers", data=body, content_type="application/json",
                           headers=_signed(made["key"], "POST", "/api/agent/v1/syslog", body))
    assert res.status_code == 401
    # Signed for another body.
    res = anon_client.post("/api/agent/v1/answers", data=body, content_type="application/json",
                           headers=_signed(made["key"], "POST", "/api/agent/v1/answers", b'{"answers": [1]}'))
    assert res.status_code == 401
    # Ten minutes old.
    res = anon_client.post("/api/agent/v1/answers", data=body, content_type="application/json",
                           headers=_signed(made["key"], "POST", "/api/agent/v1/answers", body, stamp=time.time() - 600))
    assert res.status_code == 401 and res.get_json()["code"] == "clock"
    good = _signed(made["key"], "POST", "/api/agent/v1/answers", body)
    assert anon_client.post("/api/agent/v1/answers", data=body, content_type="application/json",
                            headers=good).status_code == 200
    # The same request again: a replay.
    res = anon_client.post("/api/agent/v1/answers", data=body, content_type="application/json", headers=good)
    assert res.status_code == 401 and "replay" in res.get_json()["error"]


def test_a_signature_needs_the_bearer_key_too(client, anon_client):
    made = enrol(client)
    anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
    wrong = made["key"][:-4] + "xxxx"
    res = anon_client.get("/api/agent/v1/calls?wait=0", headers=_signed(wrong, "GET", "/api/agent/v1/calls?wait=0"))
    assert res.status_code == 401


def test_revoking_or_resetting_drops_the_pin(client, anon_client):
    made = enrol(client)
    anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
    assert client.post(f"/api/agents/{made['id']}/identity/reset").status_code == 200
    assert agent_identity.pinned(made["id"]) is None
    calls = "/api/agent/v1/calls?wait=0"
    res = anon_client.get(calls, headers=_signed(made["key"], "GET", calls))
    assert res.status_code == 401 and res.get_json()["code"] == "enrol"
    audit = client.get("/api/settings/audit").get_json()
    assert "Reset a local agent's identity" in json.dumps(audit)
    assert client.delete(f"/api/agents/{made['id']}").status_code == 200
    res = anon_client.get("/api/agent/v1/hello", headers=_signed(made["key"], "GET", "/api/agent/v1/hello"))
    assert res.status_code == 401


def test_only_admins_reset(client, anon_client):
    made = enrol(client)
    assert anon_client.post(f"/api/agents/{made['id']}/identity/reset").status_code in (401, 403)


def test_the_front_door_needs_the_agents_signature(client, anon_client):
    from flask import Flask

    made = enrol(client)
    anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
    app = Flask(__name__)
    door = {"Floorbit-Front-Door": made["key"]}
    with app.test_request_context("/checkin", headers=door):
        assert agent_link.front_door(made["key"]) is None              # the key alone: no
    signed = {**door, SIG: agent_signature(made["id"], "GET", "/checkin", b"")}
    with app.test_request_context("/checkin", headers=signed):
        assert agent_link.front_door(made["key"]) == made["id"]
        assert agent_link.front_door(made["key"]) == made["id"]      # asked twice per request: no replay
    other = ec.generate_private_key(ec.SECP256R1())
    with app.test_request_context("/checkin", headers={**door, SIG: agent_signature(made["id"], "GET", "/checkin", b"",
                                                                                   key=other)}):
        assert agent_link.front_door(made["key"]) is None


@pytest.mark.parametrize("header", ["", "t=1", "t=x,n=abcdefghijklmnopqrstuv,s=AAAA", "t=1,n=short,s=AAAA",
                                    "t=1,n=abcdefghijklmnopqrstuv,s=@@@"])
def test_a_malformed_signature_is_refused(header):
    with pytest.raises(agent_identity.IdentityError):
        agent_identity.parse(header) if header else agent_identity.verify("a", {}, "GET", "/", header, b"")


def test_the_real_agent_signs_against_this_floorbit(client, app_module, tmp_path):
    """The agent's own code (floorbit_agent/identity.py) against this side: enrol at hello, then
    every request signed. Skipped where the agent at AGENT_REF predates it."""
    agent_mod = pytest.importorskip("floorbit_agent")
    ident = pytest.importorskip("floorbit_agent.identity")
    import requests

    from tests.test_agent_program import fake_execute

    test_client = app_module.app.test_client()

    class Http:
        """requests.Session's auth on a prepared request, sent through the test client."""
        auth = None

        def _send(self, method, url, data=None, headers=None, params=None):
            req = requests.Request(method, url, data=data, headers=headers, params=params).prepare()
            if self.auth is not None:
                self.auth(req)
            sent = dict(req.headers)
            if self.auth is None:
                sent[UNSIGNED] = "1"      # as sent: the test client must not sign it for us
            r = test_client.open(req.path_url, method=method, data=req.body, headers=sent)

            class Resp:
                status_code = r.status_code

                def __init__(self):
                    self.headers = dict(r.headers)

                def json(self):
                    return r.get_json()

                def raise_for_status(self):
                    if r.status_code >= 400:
                        raise RuntimeError(f"HTTP {r.status_code}")
            resp = Resp()
            for hook in req.hooks.get("response", []):
                hook(resp)
            return resp

        def get(self, url, params=None, headers=None, timeout=None):
            return self._send("GET", url, headers=headers, params=params)

        def post(self, url, data=None, headers=None, timeout=None):
            return self._send("POST", url, data=data, headers=headers)

    key = enrol(client)["key"]
    a = agent_mod.Agent("http://hosted.example.com", key, fake_execute, http=Http(), log=lambda *_: None)
    a.use_identity(ident.Identity(str(tmp_path), log=lambda *_: None))
    hello = a.hello()
    assert hello["identity"]["pinned"] is False            # this hello enrolled it
    assert agent_identity.pinned(_id(key))["spki"].startswith(a.identity.fingerprint())
    assert a.hello()["identity"]["signed"] is True
    a.poll(wait=0)                                         # a signed long poll goes through
    a.http.auth = None
    with pytest.raises(agent_mod.IdentityRefused):
        a.poll(wait=0)
