"""A small ACME client (RFC 8555) for the agents' public certificate (floorbit/public_cert.py).

Only what Floorbit needs: one account, one name per order, the HTTP-01 challenge, revocation and
the renewal window (ARI, RFC 9773) where the CA offers it. Built on ``cryptography`` and
``requests``, which Floorbit has anyway, so no ACME library joins the image.

HTTP-01 answers are kept in the platform's shared storage (the default tenant's folder), not the
tenant's: on a hosted platform port 80 may reach any tenant's process, and each must be able to
answer for the others.
"""
import base64
import hashlib
import json
import os
import re
import time

import requests

from . import store

LETS_ENCRYPT = 'https://acme-v02.api.letsencrypt.org/directory'
CHALLENGES = 'acme-challenges'
CHALLENGE_TTL = 3600
TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{16,200}\Z')
POLL_EVERY = 2.0
POLL_FOR = 90.0
TIMEOUT = 30


class AcmeError(RuntimeError):
    pass


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _int_bytes(n, size=32):
    return n.to_bytes(size, 'big')


# ── account key ────────────────────────────────────────────────────────────────────────────────

def new_key_pem():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def _jwk(key):
    return _jwk_public(key.public_key())


def _jwk_public(public_key):
    nums = public_key.public_numbers()
    return {'crv': 'P-256', 'kty': 'EC', 'x': b64(_int_bytes(nums.x)), 'y': b64(_int_bytes(nums.y))}


def thumbprint(key):
    return thumbprint_of_public(key.public_key())


def thumbprint_of_public(public_key):
    jwk = _jwk_public(public_key)
    canon = json.dumps({k: jwk[k] for k in ('crv', 'kty', 'x', 'y')}, separators=(',', ':'), sort_keys=True)
    return b64(hashlib.sha256(canon.encode()).digest())


# ── HTTP-01 answers ────────────────────────────────────────────────────────────────────────────

def _challenge_path(token):
    return store.tenant_path(CHALLENGES, hashlib.sha256(token.encode()).hexdigest() + '.json')


def _platform():
    return store.using(tenant=store.tenant_folder(store.DEFAULT_TENANT), event='')


def put_challenge(token, answer, now=None):
    now = time.time() if now is None else now
    with _platform():
        store.write_json(_challenge_path(token), {'token': token, 'answer': answer, 'until': now + CHALLENGE_TTL})


def drop_challenge(token):
    with _platform():
        store.delete_json(_challenge_path(token))


def challenge_answer(token, now=None):
    """The key authorization for ``token`` while an order waits for it, else None."""
    if not isinstance(token, str) or not TOKEN_RE.match(token):
        return None
    now = time.time() if now is None else now
    with _platform():
        doc = store.read_json(_challenge_path(token), {}) or {}
    if doc.get('token') != token or not isinstance(doc.get('until'), (int, float)) or doc['until'] < now:
        return None
    return doc.get('answer')


# ── the client ─────────────────────────────────────────────────────────────────────────────────

class Client:
    def __init__(self, directory_url, key_pem, kid=None, session=None, sleep=time.sleep):
        from cryptography.hazmat.primitives import serialization
        self.directory_url = directory_url
        self.key = serialization.load_pem_private_key(key_pem.encode(), None)
        self.kid = kid
        self.http = session or requests.Session()
        self.sleep = sleep
        self._dir = None
        self._nonce = None

    @property
    def directory(self):
        if self._dir is None:
            resp = self.http.get(self.directory_url, timeout=TIMEOUT)
            if resp.status_code != 200:
                raise AcmeError(f'The ACME directory answered HTTP {resp.status_code}.')
            self._dir = resp.json()
        return self._dir

    def _new_nonce(self):
        resp = self.http.head(self.directory['newNonce'], timeout=TIMEOUT)
        nonce = resp.headers.get('Replay-Nonce')
        if not nonce:
            raise AcmeError('The ACME server gave no nonce.')
        return nonce

    def _sign(self, url, payload, use_jwk=False):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        nonce, self._nonce = self._nonce or self._new_nonce(), None
        protected = {'alg': 'ES256', 'nonce': nonce, 'url': url}
        if use_jwk or not self.kid:
            protected['jwk'] = _jwk(self.key)
        else:
            protected['kid'] = self.kid
        head = b64(json.dumps(protected).encode())
        body = '' if payload is None else b64(json.dumps(payload).encode())
        r, s = decode_dss_signature(self.key.sign(f'{head}.{body}'.encode(), ec.ECDSA(hashes.SHA256())))
        return {'protected': head, 'payload': body, 'signature': b64(_int_bytes(r) + _int_bytes(s))}

    def post(self, url, payload=None, use_jwk=False, ok=(200, 201)):
        """A signed POST (``payload=None``: POST-as-GET). One more try on a stale nonce."""
        for attempt in (1, 2):
            resp = self.http.post(url, data=json.dumps(self._sign(url, payload, use_jwk)),
                                  headers={'Content-Type': 'application/jose+json'}, timeout=TIMEOUT)
            self._nonce = resp.headers.get('Replay-Nonce')
            if resp.status_code in ok:
                return resp
            problem = _problem(resp)
            if attempt == 1 and problem.get('type') == 'urn:ietf:params:acme:error:badNonce':
                continue
            raise AcmeError(problem.get('detail') or f'The ACME server answered HTTP {resp.status_code}.')
        raise AcmeError('The ACME server kept refusing the nonce.')

    def account(self):
        """Register (or find) the account; returns its URL."""
        resp = self.post(self.directory['newAccount'], {'termsOfServiceAgreed': True}, use_jwk=True)
        self.kid = resp.headers.get('Location')
        if not self.kid:
            raise AcmeError('The ACME server gave the account no address.')
        return self.kid

    def _poll(self, url, done, failed):
        deadline = time.monotonic() + POLL_FOR
        while True:
            body = self.post(url).json()
            if body.get('status') in done:
                return body
            if body.get('status') in failed:
                raise AcmeError(_why(body))
            if time.monotonic() > deadline:
                raise AcmeError(f'The ACME server is still at "{body.get("status")}" after {int(POLL_FOR)} s.')
            self.sleep(POLL_EVERY)

    def issue(self, name, key_pem):
        """A certificate for ``name`` and the key in ``key_pem``: the PEM chain."""
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.x509.oid import NameOID
        if not self.kid:
            self.account()
        resp = self.post(self.directory['newOrder'], {'identifiers': [{'type': 'dns', 'value': name}]})
        order_url, order = resp.headers.get('Location'), resp.json()
        tokens = []
        try:
            for authz_url in order.get('authorizations') or []:
                authz = self.post(authz_url).json()
                if authz.get('status') == 'valid':
                    continue
                challenge = next((c for c in authz.get('challenges') or [] if c.get('type') == 'http-01'), None)
                if challenge is None or not TOKEN_RE.match(str(challenge.get('token') or '')):
                    raise AcmeError('The ACME server offered no HTTP-01 challenge.')
                token = challenge['token']
                put_challenge(token, f'{token}.{thumbprint(self.key)}')
                tokens.append(token)
                self.post(challenge['url'], {})
                self._poll(authz_url, ('valid',), ('invalid', 'revoked', 'expired', 'deactivated'))
            key = serialization.load_pem_private_key(key_pem.encode(), None)
            csr = (x509.CertificateSigningRequestBuilder()
                   .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name[:64])]))
                   .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
                   .sign(key, hashes.SHA256()))
            self.post(order['finalize'], {'csr': b64(csr.public_bytes(serialization.Encoding.DER))})
            order = self._poll(order_url, ('valid',), ('invalid',))
            pem = self.post(order['certificate']).text
        finally:
            for token in tokens:
                drop_challenge(token)
        if 'BEGIN CERTIFICATE' not in pem:
            raise AcmeError('The ACME server sent no certificate.')
        return pem

    def revoke(self, cert_pem, reason=1):
        """Revoke a certificate this account got (reason 1: key compromise)."""
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        cert = x509.load_pem_x509_certificates(cert_pem.encode())[0]
        if not self.kid:
            self.account()
        self.post(self.directory['revokeCert'],
                  {'certificate': b64(cert.public_bytes(serialization.Encoding.DER)), 'reason': reason})

    def renewal_start(self, cert_pem):
        """When the CA wants this certificate renewed (ARI), as a unix time; None when it doesn't say."""
        url = self.directory.get('renewalInfo')
        if not url:
            return None
        try:
            resp = self.http.get(f'{url.rstrip("/")}/{cert_id(cert_pem)}', timeout=TIMEOUT)
            start = (resp.json().get('suggestedWindow') or {}).get('start') if resp.status_code == 200 else None
        except (requests.RequestException, ValueError, AttributeError):
            return None
        return _when(start)


def cert_id(cert_pem):
    """The ARI identifier: the issuer's key id and the serial number."""
    from cryptography import x509
    cert = x509.load_pem_x509_certificates(cert_pem.encode())[0]
    aki = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value.key_identifier
    serial = cert.serial_number
    raw = serial.to_bytes((serial.bit_length() + 8) // 8, 'big')   # DER: a leading 0 keeps it positive
    return f'{b64(aki)}.{b64(raw)}'


def _when(text):
    import datetime
    if not isinstance(text, str):
        return None
    try:
        return datetime.datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def _problem(resp):
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _why(body):
    for authz_or_order in [body, *(body.get('challenges') or [])]:
        error = authz_or_order.get('error') if isinstance(authz_or_order, dict) else None
        if isinstance(error, dict) and error.get('detail'):
            return str(error['detail'])[:300]
    return f'The ACME server says "{body.get("status")}".'


def directory_url():
    """Let's Encrypt; FLOORBIT_ACME_DIRECTORY points elsewhere (its staging, a test CA)."""
    return (os.environ.get('FLOORBIT_ACME_DIRECTORY') or '').strip() or LETS_ENCRYPT
