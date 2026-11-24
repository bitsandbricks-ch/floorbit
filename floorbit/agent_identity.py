"""Who is on the other end of an agent request: the agent's own key, not only its bearer key
(docs/agent.md, "Identity"). Issue #1178.

The bearer key (``fba_<id>_<secret>``) alone proved too little: whoever copies it out of a
compose file or a log is the agent until someone revokes it. So each agent also has a key pair of
its own:

- **Enrolment:** the agent makes the key on its machine (it never leaves) and sends a signing
  request with its bearer key (``POST /api/agent/v1/identity``). The agents CA (agent_ca.py) signs
  a client certificate for the agent's id, and Floorbit pins the public key on the agent's record.
  The first request wins; after that only a request signed by the pinned key can change it
  (the agent's own key change), or an admin resets it (``POST /api/agents/<id>/identity/reset``).
- **Every request is signed** (``Floorbit-Agent-Signature``): method, path and query, time, a
  nonce, the agent id and the body's hash, with the pinned key. Checked here, in the app, so it
  works the same behind Traefik, any other proxy or none. A request without it is refused, except
  hello and the enrolment itself.
- **Replays:** a signature is good for ``WINDOW`` seconds around Floorbit's clock and only once
  (its nonce is remembered). The agent takes Floorbit's time from the answers' ``Date``, so a hall
  box without NTP still signs in time.
- **Revoking** the agent drops the record and so the pin: its next request fails, its open link
  closes within seconds. A reset does the same for the key alone.

The certificate itself is what the CA says about the key (agent id, 90 days, client use). The pin
is what counts here; the agent renews the certificate with the same key while it runs.
"""
import base64
import binascii
import hashlib
import re
import threading
import time

from .store import load_data, load_shared, save_data

SIGNATURE_HEADER = 'Floorbit-Agent-Signature'
SCHEME = 'floorbit-agent-v1'
RENEW_DAYS = 30              # the agent renews its client certificate this long before the end
WINDOW = 300                 # seconds a signature's time may be off Floorbit's, either way
NONCE_RE = re.compile(r'^[A-Za-z0-9_-]{16,64}\Z')
SIG_MAX = 200                # base64 of a P-256 or P-384 DER signature fits easily
# Without a pinned key, only these let the agent in: say hello, and enrol.
OPEN_PATHS = ('/api/agent/v1/hello', '/api/agent/v1/identity')

_lock = threading.Lock()
_seen = {}                   # (agent id, nonce) -> time: one process (gunicorn runs one worker)
_keys = {}                   # spki hex -> loaded public key


class IdentityError(ValueError):
    """Why a request's signature doesn't hold. ``code`` lets the agent act on it (``clock``)."""
    def __init__(self, message, code='identity'):
        super().__init__(message)
        self.code = code


def spki_of(public_key):
    from cryptography.hazmat.primitives import serialization
    der = public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def _public_pem(public_key):
    from cryptography.hazmat.primitives import serialization
    return public_key.public_bytes(serialization.Encoding.PEM,
                                   serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def _load_key(identity):
    found = _keys.get(identity['spki'])
    if found is None:
        from cryptography.hazmat.primitives import serialization
        found = serialization.load_pem_public_key(identity['public_key'].encode())
        if len(_keys) > 100:
            _keys.clear()
        _keys[identity['spki']] = found
    return found


def message(method, target, stamp, nonce, agent_id, body):
    """The bytes the agent signs. ``target`` is the path with its query (``/x?a=1``) as sent."""
    digest = hashlib.sha256(body or b'').hexdigest()
    return '\n'.join((SCHEME, method.upper(), target, stamp, nonce, agent_id, digest)).encode()


def parse(header):
    """``t=<unix>,n=<nonce>,s=<base64 signature>`` -> (t, n, signature bytes)."""
    parts = {}
    for item in str(header or '').split(','):
        k, sep, v = item.strip().partition('=')
        if sep and k in ('t', 'n', 's') and k not in parts:
            parts[k] = v.strip()
    if set(parts) != {'t', 'n', 's'} or not NONCE_RE.match(parts['n']) or len(parts['s']) > SIG_MAX:
        raise IdentityError('The agent signature header is malformed.')
    try:
        float(parts['t'])
        sig = base64.b64decode(parts['s'], validate=True)
    except (ValueError, binascii.Error):
        raise IdentityError('The agent signature header is malformed.') from None
    return parts['t'], parts['n'], sig


def pinned(agent_id, data=None):
    """The agent's pinned identity (``{spki, public_key, serial, not_after, pinned_at}``) or None."""
    data = load_shared() if data is None else data
    found = next((a for a in data.get('agents') or [] if a['id'] == agent_id), None)
    return (found or {}).get('identity') or None


def _remember(agent_id, nonce, now):
    with _lock:
        if len(_seen) > 20000 or any(now - t > 2 * WINDOW for t in list(_seen.values())[:50]):
            for k, t in list(_seen.items()):
                if now - t > 2 * WINDOW:
                    del _seen[k]
        if (agent_id, nonce) in _seen:
            raise IdentityError('The agent sent the same signed request twice; refused as a replay.')
        _seen[(agent_id, nonce)] = now


def verify(agent_id, identity, method, target, header, body, now=None):
    """Raises IdentityError unless ``header`` signs this request with the pinned key."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    if not header:
        raise IdentityError('The agent did not sign the request. Update the agent: Floorbit needs its signature.',
                            'unsigned')
    stamp, nonce, sig = parse(header)
    now = time.time() if now is None else now
    if abs(now - float(stamp)) > WINDOW:
        raise IdentityError(f"The agent's clock is more than {WINDOW // 60} minutes off Floorbit's; "
                            'it takes Floorbit\'s time from the answer and tries again.', 'clock')
    try:
        _load_key(identity).verify(sig, message(method, target, stamp, nonce, agent_id, body),
                                   ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError, TypeError):
        raise IdentityError("The request is not signed by this agent's pinned key.") from None
    _remember(agent_id, nonce, now)


def enrol(agent_id, csr_pem, signed_by_pin, now=None):
    """Sign the agent's client certificate and pin its key. ``signed_by_pin``: this request carried
    a valid signature by the key pinned now (None when nothing is pinned). Returns (cert PEM chain,
    identity record, first pin?)."""
    from cryptography import x509

    from . import agent_ca
    now = time.time() if now is None else now
    if not isinstance(csr_pem, str) or len(csr_pem) > agent_ca.CSR_MAX:
        raise agent_ca.CAError('The signing request is missing or too large.')
    try:
        public = x509.load_pem_x509_csr(csr_pem.encode()).public_key()
    except ValueError:
        raise agent_ca.CAError('The signing request is not a PEM certificate request.') from None
    spki = spki_of(public)
    with _lock:
        data = load_data()
        found = next((a for a in data.get('agents') or [] if a['id'] == agent_id), None)
        if found is None:
            raise agent_ca.CAError('No such agent.')
        current = found.get('identity')
        if current and not signed_by_pin:
            raise IdentityError('This agent already has a pinned key. Sign the request with it, or ask an admin '
                                "to reset the agent's identity.")
        pem, not_after, serial = agent_ca.sign_client(csr_pem, agent_id)
        record = {'spki': spki, 'public_key': _public_pem(public), 'serial': serial, 'not_after': not_after,
                  'issued_at': now,
                  'pinned_at': current['pinned_at'] if current and current['spki'] == spki else now}
        found['identity'] = record
        save_data(data)
    return pem, record, current is None


def reset(agent_id):
    """Forget the pinned key: the agent's next request without a signature it can make enrols
    again. Returns the agent's name."""
    with _lock:
        data = load_data()
        found = next((a for a in data.get('agents') or [] if a['id'] == agent_id), None)
        if found is None:
            from .agent_link import AgentError
            err = AgentError('No such agent.')
            err.status = 404
            raise err
        found.pop('identity', None)
        save_data(data)
    return found['name']


def public(identity):
    """What the agent's page shows."""
    if not identity:
        return None
    return {'fingerprint': identity['spki'][:32], 'not_after': identity.get('not_after'),
            'pinned_at': identity.get('pinned_at'), 'issued_at': identity.get('issued_at')}
