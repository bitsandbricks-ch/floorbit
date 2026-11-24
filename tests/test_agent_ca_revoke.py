"""Agent server certificates are short-lived and go on the CA's revocation list when the agent is
revoked (issue #1181)."""
import datetime

from cryptography import x509

from floorbit import agent_ca
from tests.test_agent import enrol, head
from tests.test_agent_settings import _csr


def _cert(client, anon_client, agent):
    client.patch(f"/api/agents/{agent['id']}/settings", json={"settings": {"cert_names": ["agent.example.com"]}})
    pem = anon_client.post("/api/agent/v1/cert", json={"csr": _csr(["agent.example.com"])},
                           headers=head(agent["key"])).get_json()["cert"]
    return x509.load_pem_x509_certificates(pem.encode())[0]


def _crl(anon_client):
    r = anon_client.get("/api/agents/ca.crl")
    assert r.status_code == 200 and r.mimetype == "application/pkix-crl"
    return x509.load_der_x509_crl(r.data)


def test_a_server_certificate_lives_90_days(client, anon_client):
    leaf = _cert(client, anon_client, enrol(client))
    life = leaf.not_valid_after_utc - leaf.not_valid_before_utc
    assert datetime.timedelta(days=89) < life <= datetime.timedelta(days=90, minutes=5)


def test_revoking_an_agent_lists_every_certificate_it_holds(client, anon_client):
    a, b = enrol(client, "Hall A"), enrol(client, "Hall B")
    first, second = _cert(client, anon_client, a), _cert(client, anon_client, a)
    other = _cert(client, anon_client, b)
    assert len(_crl(anon_client)) == 0                     # open to everyone, empty until something is revoked
    assert client.delete(f"/api/agents/{a['id']}").status_code == 200
    crl = _crl(anon_client)
    ca = x509.load_pem_x509_certificate(agent_ca.ca_pem().encode())
    assert crl.issuer == ca.subject and crl.is_signature_valid(ca.public_key())
    assert crl.get_revoked_certificate_by_serial_number(first.serial_number) is not None
    assert crl.get_revoked_certificate_by_serial_number(second.serial_number) is not None
    assert crl.get_revoked_certificate_by_serial_number(other.serial_number) is None


def test_an_expired_certificate_leaves_the_list():
    agent_ca.revoke([{"serial": "abc", "not_after": 2_000_000_000}, {"serial": "def", "not_after": 10}], now=100)
    assert [r["serial"] for r in agent_ca.revoked(now=100)] == ["abc"]
    assert agent_ca.revoked(now=2_000_000_001) == []


def test_certificates_name_the_list_when_floorbit_knows_its_address(client, anon_client, monkeypatch):
    from integrations import config
    real = config.get
    monkeypatch.setattr(config, "get",
                        lambda k, d=None: "https://floor.example.com/" if k == "PUBLIC_URL" else real(k, d))
    leaf = _cert(client, anon_client, enrol(client))
    points = leaf.extensions.get_extension_for_class(x509.CRLDistributionPoints).value
    assert [n.value for p in points for n in p.full_name] == ["https://floor.example.com/api/agents/ca.crl"]
