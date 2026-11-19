"""Each agent's settings set in Floorbit, its key fetched by the agent, its certificate signed by
Floorbit's agents CA (floorbit/agent_settings.py, floorbit/agent_ca.py, docs/agent.md)."""
import pytest

from floorbit import agent_link, sources
from tests.test_agent import enrol, head


@pytest.fixture(autouse=True)
def clean_tunnel():
    agent_link.tunnel.reset()
    agent_link._forget_cache()
    yield
    agent_link.tunnel.reset()
    agent_link._forget_cache()


@pytest.fixture
def relay_on(monkeypatch):
    registry = sources.registry
    monkeypatch.setattr(registry, "enabled", lambda spec: spec.id == "netflow-relay")


def test_settings_are_checked_saved_and_reach_only_that_agent(client, anon_client, relay_on):
    a, b = enrol(client, "Hall A"), enrol(client, "Hall B")
    bad = client.patch(f"/api/agents/{a['id']}/settings", json={"settings": {"vrrp_vips": ["not-an-address"]}})
    assert bad.status_code == 400 and "not valid" in bad.get_json()["error"]
    assert client.patch(f"/api/agents/{a['id']}/settings", json={"settings": {"allow_actions": "*"}}).status_code == 400
    assert client.patch(f"/api/agents/{a['id']}/settings",
                        json={"plugins": {"netflow-relay": {"secret_thing": 1}}}).status_code == 400
    page = client.patch(f"/api/agents/{a['id']}/settings", json={
        "settings": {"lan_url": "http://192.0.2.10:8908/", "buffer_max_mb": 512, "metrics_token": "example-token",
                     "vrrp_vips": "192.0.2.10/24, 192.0.2.11/24"},
        "plugins": {"netflow-relay": {"port": 2055}}}).get_json()
    assert page["values"] == {"lan_url": "http://192.0.2.10:8908", "buffer_max_mb": 512, "metrics_token": True,
                              "vrrp_vips": ["192.0.2.10/24", "192.0.2.11/24"]}
    relay = next(p for p in page["plugins"] if p["id"] == "netflow-relay")
    assert relay["values"] == {"port": 2055} and {f["key"] for f in relay["fields"]} == {"port", "bind"}
    assert "FLOORBIT_AGENT_ALLOW_ACTIONS" in page["local_only"]
    assert "example-token" not in str(agent_link.load_data())          # sealed at rest
    mine = anon_client.get("/api/agent/v1/plugins", headers=head(a["key"])).get_json()
    assert mine["plugins"]["netflow-relay"]["settings"]["port"] == 2055
    assert mine["agent"]["settings"]["metrics_token"] == "example-token"
    assert mine["agent"]["settings"]["buffer_max_mb"] == 512
    other = anon_client.get("/api/agent/v1/plugins", headers=head(b["key"])).get_json()
    assert other["plugins"]["netflow-relay"]["settings"]["port"] == 0 and other["agent"]["settings"] == {}
    # Cleared: the default from Settings > Plugins applies again.
    client.patch(f"/api/agents/{a['id']}/settings", json={"plugins": {"netflow-relay": {"port": None}},
                                                          "settings": {"metrics_token": None}})
    mine = anon_client.get("/api/agent/v1/plugins", headers=head(a["key"])).get_json()
    assert mine["plugins"]["netflow-relay"]["settings"]["port"] == 0
    assert "metrics_token" not in mine["agent"]["settings"]


def test_the_report_says_where_each_value_came_from(client, anon_client):
    a = enrol(client)
    sent = {"settings": {"values": {
        "lan_url": {"source": "floorbit", "value": "http://192.0.2.10:8908"},
        "metrics_token": {"source": "env", "value": "example-token", "set": True},
        "FLOORBIT_AGENT_ALLOW_ACTIONS": {"source": "env", "value": "lancache.*"},
        "SOMETHING_ELSE": {"source": "env", "value": "x"}},
        "pending": ["buffer_max_mb", "nope"], "key": "stored",
        "cert": {"not_after": 1_900_000_000, "names": ["agent.example.com"], "source": "floorbit",
                 "floorbit_ca": True}}}
    anon_client.post("/api/agent/v1/report", json={"report": sent}, headers=head(a["key"]))
    got = client.get("/api/agents").get_json()["agents"][0]["report"]["settings"]
    assert got["values"]["lan_url"] == {"source": "floorbit", "value": "http://192.0.2.10:8908"}
    assert got["values"]["metrics_token"] == {"source": "env", "set": True}           # never the token
    assert got["values"]["FLOORBIT_AGENT_ALLOW_ACTIONS"]["value"] == "lancache.*"
    assert "SOMETHING_ELSE" not in got["values"] and got["pending"] == ["buffer_max_mb"] and got["key"] == "stored"
    assert got["cert"]["names"] == ["agent.example.com"] and got["cert"]["floorbit_ca"] is True


def test_the_agent_fetches_its_new_key(client, anon_client):
    a = enrol(client)
    old = head(a["key"])
    assert anon_client.post("/api/agent/v1/key", headers=old).status_code == 409        # nobody asked
    assert client.post(f"/api/agents/{a['id']}/roll").get_json()["roll_asked"]
    assert anon_client.get("/api/agent/v1/plugins", headers=old).get_json()["agent"]["roll_key"] is True
    first = anon_client.post("/api/agent/v1/key", headers=old).get_json()["key"]
    # The answer got lost and it was asked again: the key the agent really has keeps working.
    client.post(f"/api/agents/{a['id']}/roll")
    second = anon_client.post("/api/agent/v1/key", headers=old).get_json()["key"]
    assert first != second
    assert anon_client.get("/api/agent/v1/plugins", headers=old).status_code == 200
    assert anon_client.get("/api/agent/v1/plugins", headers=head(first)).status_code == 401
    cfg = anon_client.get("/api/agent/v1/plugins", headers=head(second)).get_json()
    assert cfg["agent"]["roll_key"] is False
    assert anon_client.get("/api/agent/v1/plugins", headers=old).status_code == 401    # the new one is in use
    assert client.post("/api/agents/roll").get_json() == {"asked": 1}


def _csr(names):
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    sans = [x509.IPAddress(ipaddress.ip_address(n)) if n[0].isdigit() else x509.DNSName(n) for n in names]
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
           .add_extension(x509.SubjectAlternativeName(sans), critical=False).sign(key, hashes.SHA256()))
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def test_the_ca_signs_only_the_names_set_for_the_agent(client, anon_client):
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec
    a = enrol(client)
    asked = anon_client.post("/api/agent/v1/cert", json={"csr": _csr(["agent.example.com"])}, headers=head(a["key"]))
    assert asked.status_code == 400 and "cert_names" in asked.get_json()["error"]
    assert client.post(f"/api/agents/{a['id']}/cert").status_code == 400
    names = ["agent.example.com", "192.0.2.10"]
    client.patch(f"/api/agents/{a['id']}/settings", json={"settings": {"cert_names": names}})
    cfg = anon_client.get("/api/agent/v1/plugins", headers=head(a["key"])).get_json()
    assert cfg["agent"]["cert"] == {"names": ["agent.example.com", "192.0.2.10"], "asked": 0}
    assert anon_client.post("/api/agent/v1/cert", json={"csr": "nonsense"}, headers=head(a["key"])).status_code == 400
    # It asks for someone else's site as well: only the names set here go in.
    pem = anon_client.post("/api/agent/v1/cert", json={"csr": _csr(["www.example.org", "agent.example.com"])},
                           headers=head(a["key"])).get_json()["cert"]
    leaf, ca = x509.load_pem_x509_certificates(pem.encode())
    sans = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert sans.get_values_for_type(x509.DNSName) == ["agent.example.com"]
    assert [str(i) for i in sans.get_values_for_type(x509.IPAddress)] == ["192.0.2.10"]
    ca.public_key().verify(leaf.signature, leaf.tbs_certificate_bytes, ec.ECDSA(leaf.signature_hash_algorithm))
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is True
    download = client.get("/api/agents/ca.pem")
    assert download.status_code == 200 and x509.load_pem_x509_certificate(download.data).subject == ca.subject
    assert anon_client.get("/api/agents/ca.pem").status_code in (401, 403)
    page = client.get(f"/api/agents/{a['id']}/settings").get_json()
    assert page["cert"]["names"] == ["agent.example.com", "192.0.2.10"]
    assert client.post(f"/api/agents/{a['id']}/cert").get_json()["cert_asked"]
