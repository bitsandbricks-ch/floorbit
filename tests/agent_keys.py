"""Test keys for local agents, which sign their requests (floorbit/agent_identity.py). One module
so conftest and the tests share the same keys."""

AGENT_KEYS = {}                 # agent id -> the test's private key for it
UNSIGNED = "Floorbit-Test-Unsigned"   # a test that wants a request as an old or forged agent sends it


def agent_private_key(agent_id):
    from cryptography.hazmat.primitives.asymmetric import ec
    if agent_id not in AGENT_KEYS:
        AGENT_KEYS[agent_id] = ec.generate_private_key(ec.SECP256R1())
    return AGENT_KEYS[agent_id]


def agent_csr(agent_id, key=None):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"agent {agent_id}")]))
           .sign(key or agent_private_key(agent_id), hashes.SHA256()))
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def agent_signature(agent_id, method, target, body, key=None, stamp=None):
    import base64
    import secrets
    import time

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    from floorbit import agent_identity
    stamp = f"{time.time() if stamp is None else stamp:.3f}"
    nonce = secrets.token_urlsafe(18)
    sig = (key or agent_private_key(agent_id)).sign(
        agent_identity.message(method, target, stamp, nonce, agent_id, body), ec.ECDSA(hashes.SHA256()))
    return f"t={stamp},n={nonce},s={base64.b64encode(sig).decode()}"
