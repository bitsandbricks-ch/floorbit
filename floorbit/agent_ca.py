"""Floorbit's own certificate authority for its local agents (docs/agent.md, "Certificates").

The front door and the telemetry listener on an agent answer HTTPS with a certificate. Each agent
makes its own key and sends a signing request; Floorbit signs it with this CA. Crew devices
install the CA once (``GET /api/agents/ca.pem``) and then trust every agent, in every hall.

- The agent's private key never leaves the agent; the CA's key is sealed with the vault.
- A certificate names only what an admin listed for that agent (its ``cert_names`` setting),
  whatever the request asks for: an agent can't get a certificate for someone else's site.
- 397 days, the longest phones and browsers accept for a server certificate; the agent asks again
  30 days before the end.
"""
import datetime
import ipaddress
import threading

from .store import load_data, save_data

KEY = 'agent_ca'
SLOT = 'agent-ca:key'
CA_DAYS = 3650
CERT_DAYS = 397
RENEW_DAYS = 30
CSR_MAX = 8192

_lock = threading.Lock()


class CAError(ValueError):
    pass


def _now():
    return datetime.datetime.now(datetime.UTC)


def _make():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Floorbit'),
                      x509.NameAttribute(NameOID.COMMON_NAME, 'Floorbit local agents CA')])
    start = _now() - datetime.timedelta(minutes=5)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(start)
            .not_valid_after(start + datetime.timedelta(days=CA_DAYS))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                         content_commitment=False, key_encipherment=False, data_encipherment=False,
                                         key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    return cert.public_bytes(serialization.Encoding.PEM).decode(), key_pem


def ca_pem():
    """The CA certificate (made on first use), for crew devices and for the agents' chains."""
    from . import vault
    found = (load_data().get(KEY) or {})
    if found.get('cert'):
        return found['cert']
    with _lock:
        data = load_data()
        found = data.get(KEY) or {}
        if not found.get('cert'):
            cert, key = _make()
            data[KEY] = {'cert': cert, 'key': vault.seal(SLOT, key), 'made_at': _now().timestamp()}
            save_data(data)
            return cert
        return found['cert']


def _ca():
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    from . import vault
    ca_pem()
    found = load_data().get(KEY) or {}
    try:
        key = serialization.load_pem_private_key(vault.open_(SLOT, found['key']).encode(), None)
    except vault.VaultError as exc:
        raise CAError(f'The agents CA key cannot be opened: {exc}') from None
    return x509.load_pem_x509_certificate(found['cert'].encode()), key


def _sans(names):
    from cryptography import x509
    out = []
    for name in names:
        try:
            out.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            out.append(x509.DNSName(name.lower()))
    return out


def sign(csr_pem, names):
    """A certificate for the key in ``csr_pem``, naming only ``names``. Returns (cert PEM with the
    CA after it, not_after as a unix time)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    if not names:
        raise CAError('List the names this agent is reached by (cert_names) before it can get a certificate.')
    if not isinstance(csr_pem, str) or len(csr_pem) > CSR_MAX:
        raise CAError('The signing request is missing or too large.')
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode())
    except ValueError:
        raise CAError('The signing request is not a PEM certificate request.') from None
    if not csr.is_signature_valid:
        raise CAError('The signing request is not signed by its own key.')
    public = csr.public_key()
    if not (isinstance(public, ec.EllipticCurvePublicKey)
            or (isinstance(public, rsa.RSAPublicKey) and public.key_size >= 2048)):
        raise CAError('The signing request needs an EC key or an RSA key of 2048 bits or more.')
    ca_cert, ca_key = _ca()
    start = _now() - datetime.timedelta(minutes=5)
    end = start + datetime.timedelta(days=CERT_DAYS)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0][:64])]))
            .issuer_name(ca_cert.subject).public_key(public)
            .serial_number(x509.random_serial_number()).not_valid_before(start).not_valid_after(end)
            .add_extension(x509.SubjectAlternativeName(_sans(names)), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return pem + ca_cert.public_bytes(serialization.Encoding.PEM).decode(), end.timestamp()
