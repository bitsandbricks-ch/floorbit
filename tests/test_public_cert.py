"""The agents' Let's Encrypt certificate (floorbit/public_cert.py, floorbit/acme.py), against a fake
ACME server that checks the signatures and the HTTP-01 answer through Floorbit's own route."""
import base64
import datetime
import json

import pytest
from cryptography import x509
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.x509.oid import NameOID

from floorbit import acme, agent_link, hosting, public_cert
from tests.test_agent import enrol, head

BASE = 'https://acme.example.com'


def _unb64(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


class Resp:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code = status
        self._body = body
        self.headers = {'Replay-Nonce': 'n-next', **(headers or {})}
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError('no json')
        return self._body


class FakeAcme:
    """Just enough of RFC 8555 to issue, revoke and suggest a renewal window."""

    def __init__(self, web):
        self.web = web            # Floorbit's test client: the HTTP-01 check goes through its route
        self.accounts = {}
        self.ca_key = ec.generate_private_key(ec.SECP256R1())
        self.issued, self.revoked, self.checked = [], [], []
        self.nonces = 0
        self.bad_nonce_once = True
        self.state = {}
        self.dns = True           # public DNS and port 80 reach Floorbit (public_cert.reachable)
        self.probes = 0
        self.ca_sees_404 = False  # Let's Encrypt's own check fails anyway

    def get(self, url, timeout=None, allow_redirects=True):
        if url.startswith('http://') and '/.well-known/acme-challenge/' in url:
            self.probes += 1
            if not self.dns:
                raise ConnectionError('no such name')
            got = self.web.get(url[url.index('/.well-known/'):])
            return Resp(got.status_code, text=got.get_data(as_text=True))
        if url == f'{BASE}/directory':
            return Resp(body={k: f'{BASE}/{k}' for k in ('newNonce', 'newAccount', 'newOrder', 'revokeCert',
                                                           'renewalInfo')})
        if url.startswith(f'{BASE}/renewalInfo/'):
            return Resp(body={'suggestedWindow': {'start': '2030-01-01T00:00:00Z', 'end': '2030-01-02T00:00:00Z'}})
        return Resp(404, {})

    def head(self, url, timeout=None):
        self.nonces += 1
        return Resp(headers={'Replay-Nonce': f'n{self.nonces}'})

    def _verify(self, url, raw):
        jws = json.loads(raw)
        protected = json.loads(_unb64(jws['protected']))
        assert protected['url'] == url and protected['alg'] == 'ES256' and protected['nonce']
        if 'jwk' in protected:
            jwk = protected['jwk']
            pub = ec.EllipticCurvePublicNumbers(int.from_bytes(_unb64(jwk['x']), 'big'),
                                                int.from_bytes(_unb64(jwk['y']), 'big'),
                                                ec.SECP256R1()).public_key()
            kid = f'{BASE}/acct/{len(self.accounts) + 1}'
            for k, v in self.accounts.items():
                if v.public_numbers() == pub.public_numbers():
                    kid = k
            self.accounts[kid] = pub
        else:
            kid = protected['kid']
            pub = self.accounts[kid]
        sig = _unb64(jws['signature'])
        der = encode_dss_signature(int.from_bytes(sig[:32], 'big'), int.from_bytes(sig[32:], 'big'))
        pub.verify(der, f"{jws['protected']}.{jws['payload']}".encode(), ec.ECDSA(hashes.SHA256()))
        payload = json.loads(_unb64(jws['payload'])) if jws['payload'] else None
        return kid, payload

    def post(self, url, data=None, headers=None, timeout=None):
        if self.bad_nonce_once:
            self.bad_nonce_once = False
            return Resp(400, {'type': 'urn:ietf:params:acme:error:badNonce', 'detail': 'stale'})
        kid, payload = self._verify(url, data)
        path = url[len(BASE) + 1:]
        if path == 'newAccount':
            return Resp(201, {'status': 'valid'}, {'Location': kid})
        if path == 'newOrder':
            name = payload['identifiers'][0]['value']
            self.state = {'name': name, 'token': f'tok{len(self.issued)}' + 'x' * 30, 'authz': 'pending',
                          'order': 'pending', 'kid': kid}
            return Resp(201, {'status': 'pending', 'authorizations': [f'{BASE}/authz/1'],
                              'finalize': f'{BASE}/finalize/1'}, {'Location': f'{BASE}/order/1'})
        if path == 'authz/1':
            return Resp(body={'status': self.state['authz'], 'challenges': [
                {'type': 'dns-01', 'url': f'{BASE}/chall/dns', 'token': 'dnsdnsdnsdnsdnsdnsdns'},
                {'type': 'http-01', 'url': f'{BASE}/chall/1', 'token': self.state['token']}]})
        if path == 'chall/1':
            token = self.state['token']
            got = self.web.get(f'/.well-known/acme-challenge/{token}' + ('x' if self.ca_sees_404 else ''))
            thumb = acme.thumbprint_of_public(self.accounts[self.state['kid']])
            ok = got.status_code == 200 and got.get_data(as_text=True) == f'{token}.{thumb}'
            self.checked.append(ok)
            self.state['authz'] = 'valid' if ok else 'invalid'
            return Resp(body={'status': 'processing'})
        if path == 'finalize/1':
            csr = x509.load_der_x509_csr(_unb64(payload['csr']))
            assert csr.is_signature_valid
            sans = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            assert sans.get_values_for_type(x509.DNSName) == [self.state['name']]
            self.state['pem'] = self._sign(csr)
            self.state['order'] = 'valid'
            return Resp(body={'status': 'processing'})
        if path == 'order/1':
            return Resp(body={'status': self.state['order'], 'certificate': f'{BASE}/cert/1'})
        if path == 'cert/1':
            self.issued.append(self.state['pem'])
            return Resp(text=self.state['pem'])
        if path == 'revokeCert':
            self.revoked.append(payload)
            return Resp(200, None, text='')
        return Resp(404, {'detail': 'unknown'})

    def _sign(self, csr):
        now = datetime.datetime.now(datetime.UTC)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Fake ACME CA')])
        cert = (x509.CertificateBuilder().subject_name(csr.subject).issuer_name(name).public_key(csr.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now)
                .not_valid_after(now + datetime.timedelta(days=90))
                .add_extension(csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value, False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.ca_key.public_key()), False)
                .sign(self.ca_key, hashes.SHA256()))
        return cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setenv('FLOORBIT_ACME_DIRECTORY', f'{BASE}/directory')
    agent_link.tunnel.reset()
    agent_link._forget_cache()
    yield
    agent_link.tunnel.reset()
    agent_link._forget_cache()


@pytest.fixture
def fake(anon_client):
    return FakeAcme(anon_client)


def _agent_csr():
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'agent')])).sign(key, hashes.SHA256()))
    return key, csr.public_bytes(serialization.Encoding.PEM).decode()


def test_without_a_domain_nothing_changes(client, anon_client, fake):
    a = enrol(client)
    assert public_cert.name() is None and not public_cert.due()
    assert not public_cert.run(session=fake, sleep=lambda s: None)
    assert 'public_cert' not in anon_client.get('/api/agent/v1/plugins', headers=head(a['key'])).get_json()['agent']
    _, csr = _agent_csr()
    asked = anon_client.post('/api/agent/v1/cert', json={'csr': csr, 'public': True}, headers=head(a['key']))
    assert asked.status_code == 409


def test_the_platform_domain_is_set_by_its_admins(client):
    assert client.get('/api/platform/agent-domain').get_json()['domain'] == ''
    assert client.put('/api/platform/agent-domain', json={'domain': 'not a domain'}).status_code == 400
    assert client.put('/api/platform/agent-domain', json={'domain': 'Example.COM.'}).get_json() == {
        'domain': 'example.com', 'setting': 'example.com'}
    assert hosting.agent_domain() == 'example.com'
    assert public_cert.name() == 'default.agent.example.com'
    assert [t['id'] for t in hosting.tenants()] == ['default']      # the list is still there


@pytest.mark.parametrize('url, domain', [
    ('https://floor.example.com', 'example.com'),
    ('https://floor.lan.example.org:8443/x', 'lan.example.org'),
    ('https://example.net', 'example.net'),
    ('http://192.0.2.10:5000', ''),
    ('http://localhost:5000', ''),
    ('', ''),
])
def test_the_domain_comes_from_the_platform_address(client, monkeypatch, url, domain):
    monkeypatch.setenv('PUBLIC_URL', url)
    assert hosting.derived_domain() == domain and hosting.agent_domain() == domain
    if domain:
        assert public_cert.name() == f'default.agent.{domain}'


def test_an_admin_overrides_or_turns_off_the_derived_domain(client, monkeypatch):
    monkeypatch.setenv('PUBLIC_URL', 'https://floor.example.com')
    got = client.get('/api/platform/agent-domain').get_json()
    assert got['domain'] == 'example.com' and got['setting'] == '' and got['derived'] == 'example.com'
    assert client.put('/api/platform/agent-domain', json={'domain': 'off'}).get_json() == {
        'domain': '', 'setting': 'off'}
    assert public_cert.name() is None and not public_cert.due()
    put = client.put('/api/platform/agent-domain', json={'domain': 'example.net'})
    assert put.get_json()['domain'] == 'example.net'
    assert client.put('/api/platform/agent-domain', json={'domain': ''}).get_json() == {
        'domain': 'example.com', 'setting': ''}


def test_nothing_is_ordered_until_dns_and_port_80_reach_floorbit(client, fake, monkeypatch):
    monkeypatch.setenv('PUBLIC_URL', 'https://floor.example.com')
    fake.dns = False
    assert public_cert.due()
    assert not public_cert.run(session=fake, now=1_000, sleep=lambda s: None)
    assert fake.issued == [] and fake.accounts == {}           # Let's Encrypt was never asked
    status = public_cert.status()
    assert status['waiting'] and status['checked_at'] == 1_000 and not status['failed_at']
    assert public_cert.due(now=1_060)                          # not a failure: asked again next check
    fake.dns = True
    assert public_cert.run(session=fake, sleep=lambda s: None)
    assert len(fake.issued) == 1 and public_cert.status()['waiting'] is None


def test_the_tenant_gets_one_certificate_and_each_agent_its_key_sealed(client, anon_client, fake):
    hosting.set_agent_domain('example.com')
    a, b = enrol(client, 'Hall A'), enrol(client, 'Hall B')
    assert public_cert.due()
    assert public_cert.run(session=fake, sleep=lambda s: None)
    assert fake.checked == [True] and len(fake.issued) == 1
    assert not public_cert.due()                                     # 90 days left, ARI says 2030
    assert public_cert.status()['name'] == 'default.agent.example.com'
    # The challenge answers are gone once the order is done.
    assert anon_client.get(f"/.well-known/acme-challenge/{fake.state['token']}").status_code == 404

    cfg = anon_client.get('/api/agent/v1/plugins', headers=head(a['key'])).get_json()['agent']
    assert cfg['public_cert']['name'] == 'default.agent.example.com' and cfg['public_cert']['asked'] > 0
    key_a, csr_a = _agent_csr()
    got = anon_client.post('/api/agent/v1/cert', json={'csr': csr_a, 'public': True}, headers=head(a['key']))
    assert got.status_code == 200 and got.headers['Cache-Control'] == 'no-store'
    found = got.get_json()
    assert found['cert'] == fake.issued[0] and found['name'] == 'default.agent.example.com'
    key_pem = public_cert.open_sealed(key_a, found['key'])
    leaf = x509.load_pem_x509_certificate(found['cert'].encode())
    tls_key = serialization.load_pem_private_key(key_pem.encode(), None)
    assert tls_key.public_key().public_numbers() == leaf.public_key().public_numbers()
    # Only that agent can open it.
    other, _ = _agent_csr()
    with pytest.raises(InvalidTag):
        public_cert.open_sealed(other, found['key'])
    assert key_pem not in json.dumps(agent_link.load_data())        # sealed at rest
    assert agent_link.load_data()['agent_public_cert']['key'].startswith('v1:')
    # A forged request (another key's signature) is refused.
    bad = csr_a.replace('MI', 'MJ', 1)
    assert anon_client.post('/api/agent/v1/cert', json={'csr': bad, 'public': True},
                            headers=head(a['key'])).status_code == 409
    # Agents without "public" still get the CA's, for their own names.
    assert anon_client.post('/api/agent/v1/cert', json={'csr': csr_a}, headers=head(b['key'])).status_code == 400

    # The revoked agent had the key: revoke, new key, new certificate for the rest.
    assert client.delete(f"/api/agents/{a['id']}").status_code == 200
    assert public_cert.due()
    assert public_cert.run(session=fake, sleep=lambda s: None)
    assert len(fake.revoked) == 1 and fake.revoked[0]['reason'] == 1 and len(fake.issued) == 2
    key_b, csr_b = _agent_csr()
    found_b = anon_client.post('/api/agent/v1/cert', json={'csr': csr_b, 'public': True},
                               headers=head(b['key'])).get_json()
    assert found_b['cert'] == fake.issued[1] and public_cert.open_sealed(key_b, found_b['key']) != key_pem


def test_a_revoked_agent_that_never_had_the_key_changes_nothing(client, fake):
    hosting.set_agent_domain('example.com')
    a = enrol(client)
    assert public_cert.run(session=fake, sleep=lambda s: None)
    client.delete(f"/api/agents/{a['id']}")
    assert not public_cert.due() and fake.revoked == []


def test_a_failed_check_is_kept_and_tried_again_later(client, fake, monkeypatch):
    hosting.set_agent_domain('example.com')
    fake.ca_sees_404 = True
    assert not public_cert.run(session=fake, now=1_000, sleep=lambda s: None)
    status = public_cert.status()
    assert status['not_after'] is None and status['failed_at'] == 1_000 and status['error']
    assert not public_cert.due(now=1_000 + 60)
    assert public_cert.due(now=1_000 + public_cert.RETRY_AFTER)


def test_renewal_follows_the_end_and_the_renewal_window(client, fake):
    hosting.set_agent_domain('example.com')
    assert public_cert.run(session=fake, sleep=lambda s: None)
    st = agent_link.load_data()['agent_public_cert']
    assert st['renew_at'] == datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC).timestamp()
    assert public_cert.due(now=st['not_after'] - 29 * 86400)
    assert not public_cert.due(now=st['not_after'] - 31 * 86400)
    # A new domain is a new name: a new certificate.
    hosting.set_agent_domain('example.net')
    assert public_cert.due() and public_cert.ready() is None


def test_unknown_challenges_are_404(anon_client):
    assert anon_client.get('/.well-known/acme-challenge/' + 'a' * 40).status_code == 404
    assert anon_client.get('/.well-known/acme-challenge/short').status_code == 404
