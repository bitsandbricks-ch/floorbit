"""A Let's Encrypt certificate for each tenant's agents (issue #1026, docs/agent.md "Certificates").

Laptops in the hall reach the agent's front door as ``<tenant>.agent.<domain>``. The domain comes
from the platform's own address (floor.example.com gives example.com; ``flask tenants agent-domain``
overrides it or turns it off). Nothing needs switching on: once public DNS points the name at the
platform and port 80 reaches Floorbit (``reachable``, checked every few minutes), Floorbit gets a
certificate for it from Let's Encrypt (HTTP-01) and hands it to every agent of the tenant. The hall's
DNS points the same name at the agent.

- **One certificate per tenant**, so all its agents share one key. Floorbit makes a new key on every
  issue, keeps it sealed with the vault, and gives it to an agent only encrypted to that agent's own
  key (the one in its certificate request, which never leaves the agent): ECDH on P-256, HKDF-SHA256,
  AES-256-GCM. Each hand-over is in the audit log.
- **Renewal** 30 days before the end, or earlier when the CA's renewal window (ARI) says so.
- **A revoked agent had the key:** the certificate is revoked and a new one, with a new key, goes to
  the agents that remain.
- **No domain:** nothing changes; agents use Floorbit's own CA (agent_ca.py).
"""
import base64
import logging
import os
import secrets
import threading
import time

from . import acme, hosting, store

KEY = 'agent_public_cert'
SLOT = 'agent-public-cert:key'
ACCOUNT_SLOT = 'agent-public-cert:account'
RENEW_DAYS = 30
RETRY_AFTER = 3600
CHECK_EVERY = 600
PROBE_TIMEOUT = 10
INFO = b'floorbit agent tls key v1'
ALG = 'ECDH-ES+A256GCM'

log = logging.getLogger(__name__)
_lock = threading.Lock()
_wake = threading.Event()


class PublicCertError(ValueError):
    pass


def name():
    """``<tenant>.agent.<domain>``, or None without a platform domain."""
    domain = hosting.agent_domain()
    return f'{store.current_tenant()}.agent.{domain}' if domain else None


def _state(data=None):
    found = (data if data is not None else store.load_data()).get(KEY)
    return found if isinstance(found, dict) else {}


def _change(fn):
    with _lock:
        data = store.load_data()
        st = dict(_state(data))
        fn(st)
        data[KEY] = st
        store.save_data(data)
        return st


def ready():
    """The current certificate when it is for today's name: ``{name, cert, not_after, issued_at}``."""
    want = name()
    st = _state()
    if not want or st.get('name') != want or not st.get('cert') or not st.get('key'):
        return None
    return st


def status():
    """For the agents page: the name, until when, the last error. No key, no PEM."""
    want = name()
    if not want:
        return None
    st = _state()
    current = st.get('name') == want and st.get('cert')
    waiting = st.get('waiting') if st.get('waiting', {}).get('name') == want else None
    return {'name': want, 'not_after': st.get('not_after') if current else None,
            'issued_at': st.get('issued_at') if current else None,
            'error': st.get('error'), 'failed_at': st.get('failed_at'),
            'waiting': (waiting or {}).get('reason'), 'checked_at': (waiting or {}).get('at')}


def block():
    """What goes into each agent's config (agent_settings.agent_block): the name and when it last
    changed, so an agent fetches the new one at its next pull."""
    st = ready()
    return {'name': st['name'], 'asked': st.get('issued_at') or 0} if st else None


# ── the key for one agent ──────────────────────────────────────────────────────────────────────

def _agent_public_key(csr_pem):
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        csr = x509.load_pem_x509_csr(str(csr_pem or '').encode())
    except ValueError:
        raise PublicCertError('The signing request is not a PEM certificate request.') from None
    if not csr.is_signature_valid:
        raise PublicCertError('The signing request is not signed by its own key.')
    key = csr.public_key()
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise PublicCertError('The agent key must be an EC P-256 key. Update the agent.')
    return key


def _kdf(shared, epk_raw):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=epk_raw, info=INFO).derive(shared)


def seal_to(public_key, text):
    """``text`` encrypted so only the holder of ``public_key``'s private key can read it."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    eph = ec.generate_private_key(ec.SECP256R1())
    epk = eph.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    nonce = os.urandom(12)
    data = AESGCM(_kdf(eph.exchange(ec.ECDH(), public_key), epk)).encrypt(nonce, text.encode(), INFO)
    enc = base64.b64encode
    return {'alg': ALG, 'epk': enc(epk).decode(), 'nonce': enc(nonce).decode(), 'data': enc(data).decode()}


def open_sealed(private_key, box):
    """The other half of ``seal_to``, as the agent does it (floorbit-agent hosted.py)."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not isinstance(box, dict) or box.get('alg') != ALG:
        raise PublicCertError('Unknown key envelope.')
    epk = base64.b64decode(box['epk'])
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), epk)
    key = _kdf(private_key.exchange(ec.ECDH(), peer), epk)
    return AESGCM(key).decrypt(base64.b64decode(box['nonce']), base64.b64decode(box['data']), INFO).decode()


def bundle(agent_id, csr_pem, now=None):
    """The tenant's certificate for one agent: ``{name, cert, key}``, the key sealed to the agent's
    own key from ``csr_pem``. PublicCertError when there is none (yet)."""
    from . import agent_settings, vault
    now = time.time() if now is None else now
    public_key = _agent_public_key(csr_pem)
    st = ready()
    if st is None:
        raise PublicCertError("The agents' Let's Encrypt certificate isn't there yet. The agent asks again later.")
    try:
        key_pem = vault.open_(SLOT, st['key'])
    except vault.VaultError as exc:
        log.error("The agents' certificate key cannot be opened: %s", exc)
        raise PublicCertError("The certificate's key cannot be opened. The server log says why.") from None
    agent_settings.mark_public_cert(agent_id, now)
    return {'name': st['name'], 'cert': st['cert'], 'key': seal_to(public_key, key_pem)}


# ── getting and renewing it ────────────────────────────────────────────────────────────────────

def _not_after(pem):
    from cryptography import x509
    return x509.load_pem_x509_certificates(pem.encode())[0].not_valid_after_utc.timestamp()


def due(now=None):
    """Whether the worker should ask the CA now."""
    now = time.time() if now is None else now
    want = name()
    if not want:
        return False
    st = _state()
    if st.get('failed_at') and now - st['failed_at'] < RETRY_AFTER:
        return False
    if st.get('revoke') or st.get('name') != want or not st.get('cert'):
        return True
    return now >= min((st.get('not_after') or 0) - RENEW_DAYS * 86400, st.get('renew_at') or float('inf'))


def reachable(want, session=None):
    """Whether ``http://<want>/.well-known/acme-challenge/...`` reaches this Floorbit: public DNS has
    the name and port 80 is routed. Asked before every order, so a platform whose DNS isn't there yet
    never counts against Let's Encrypt's limits. Returns (True, '') or (False, why)."""
    if session is None:
        import requests as session
    token = 'probe-' + secrets.token_urlsafe(24)
    answer = secrets.token_urlsafe(24)
    acme.put_challenge(token, answer)
    try:
        got = session.get(f'http://{want}/.well-known/acme-challenge/{token}', timeout=PROBE_TIMEOUT,
                          allow_redirects=False)
        if got.status_code == 200 and got.text.strip() == answer:
            return True, ''
        return False, f'http://{want} answered {got.status_code}, not this Floorbit.'
    except Exception as exc:  # noqa: BLE001  # DNS, refused, timeout: all mean "not yet"
        return False, f'http://{want} cannot be reached ({type(exc).__name__}).'
    finally:
        acme.drop_challenge(token)


def _client(st, session=None, sleep=time.sleep):
    from . import vault
    account = st.get('account') or {}
    directory = acme.directory_url()
    if account.get('key') and account.get('directory') == directory:
        key_pem, kid = vault.open_(ACCOUNT_SLOT, account['key']), account.get('kid')
    else:
        key_pem, kid = acme.new_key_pem(), None
    return acme.Client(directory, key_pem, kid=kid, session=session, sleep=sleep), key_pem


def run(now=None, session=None, sleep=time.sleep):
    """Revoke (when asked) and get a new certificate. Returns True when it got one."""
    from . import audit, vault
    now = time.time() if now is None else now
    want = name()
    if not want:
        return False
    st = _state()
    try:
        client, account_key = _client(st, session=session, sleep=sleep)
        if st.get('revoke') and st.get('cert'):
            try:
                client.revoke(st['cert'])
                audit.record('agents', "Revoked the agents' Let's Encrypt certificate", 'Floorbit', st.get('name'))
                # Revoked is revoked, even if no new one can be ordered right now.
                _change(lambda s: [s.pop(k, None) for k in ('cert', 'key', 'revoke')])
            except acme.AcmeError as exc:     # a new key still replaces it below
                log.warning("Could not revoke the agents' certificate: %s", exc)
        ok, why = reachable(want, session=session)
        if not ok:
            # Not a failure: DNS or port 80 isn't there yet. Asked again at the next check.
            _change(lambda s: s.update(waiting={'name': want, 'reason': why, 'at': now}))
            return False
        key_pem = acme.new_key_pem()
        pem = client.issue(want, key_pem)
        renew_at = client.renewal_start(pem)
    except (acme.AcmeError, OSError, ValueError) as exc:
        detail = str(exc)[:300] or type(exc).__name__
        log.warning("Let's Encrypt certificate for %s: %s", want, detail)
        _change(lambda s: s.update(failed_at=now, error=detail))
        return False
    except Exception as exc:  # noqa: BLE001  # requests' errors: the worker tries again later
        detail = f'{type(exc).__name__}: {exc}'[:300]
        _change(lambda s: s.update(failed_at=now, error=detail))
        return False
    sealed_key = vault.seal(SLOT, key_pem)
    sealed_account = vault.seal(ACCOUNT_SLOT, account_key)

    def keep(s):
        s.clear()
        s.update(name=want, cert=pem, key=sealed_key, issued_at=now, not_after=_not_after(pem),
                 renew_at=renew_at, account={'key': sealed_account, 'kid': client.kid,
                                             'directory': client.directory_url})
    _change(keep)
    audit.record('agents', "Got the agents' certificate from Let's Encrypt", 'Floorbit', want)
    _push()
    return True


def _push():
    from . import agent_plugins
    try:
        agent_plugins.reload_agents()
    except Exception as exc:  # noqa: BLE001  # they pull it within a minute anyway
        log.info('Could not tell the agents at once: %s', exc)


def agent_revoked(record):
    """An agent that had the key was revoked: the worker revokes the certificate and gets a new one."""
    if not isinstance(record, dict) or not record.get('public_cert_at') or not _state().get('cert'):
        return False
    _change(lambda s: s.update(revoke=True, failed_at=None))
    _wake.set()
    return True


def wake():
    _wake.set()


def _loop(app, stop):
    from . import cluster
    while not stop.is_set():
        _wake.wait(CHECK_EVERY)
        _wake.clear()
        try:
            # The leader only: two pods would order two certificates.
            if cluster.leading() and due():
                with app.app_context():
                    run()
        except Exception as exc:  # noqa: BLE001  # the loop must outlive one bad answer
            log.warning("Let's Encrypt worker: %s", exc)


def init_app(app, start_background=True):
    if not start_background:
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(app, stop), name='public-cert', daemon=True).start()
    _wake.set()      # look once at start
    return stop
