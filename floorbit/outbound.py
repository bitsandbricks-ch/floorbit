"""Where the server's own HTTP requests may go (issue #505).

Admins set many URLs: NetBox, LibreNMS, OIDC, seat sources, webhooks, Loki and plugin base URLs. On a
hosted Floorbit each of them could make the hosting side send requests into its own network. So every
connection that ``requests`` (urllib3) opens is checked against the address it actually reached,
after DNS: a name that resolves to an allowed address when it is saved and to the metadata service a
minute later (DNS rebinding) is still refused.

- Always refused: link-local (``169.254.0.0/16``, ``fe80::/10``, where clouds keep their metadata
  service), unspecified and multicast, also inside IPv6 (``::ffff:``, NAT64, 6to4); see
  ``probes.unreachable``.
- ``OUTBOUND_BLOCK_NETS`` (comma-separated networks) refuses more, for a hosted Floorbit: loopback and
  the hosting network's own ranges, for example ``127.0.0.0/8,::1/128,10.42.0.0/16``. Self-hosted
  installs leave it empty, because NetBox and LibreNMS sit on the LAN.

``install()`` puts the check into urllib3's connection classes once, so every caller is covered
without each one having to remember it.
"""
import ipaddress

from urllib3 import connection, connectionpool

from integrations import config

from . import probes


class Refused(OSError):
    """urllib3 turns this into a NewConnectionError, and requests into a ConnectionError."""


def _block_nets():
    out = []
    for entry in (config.get('OUTBOUND_BLOCK_NETS', '') or '').split(','):
        try:
            out.append(ipaddress.ip_network(entry.strip(), strict=False))
        except ValueError:
            continue
    return out


def refused(addr):
    """Why the server won't talk to ``addr`` (an address string), or None."""
    try:
        ip = ipaddress.ip_address(str(addr).split('%')[0])
    except ValueError:
        return None
    if probes.unreachable(addr):
        return f'Refused: {ip} is a link-local, unspecified or multicast address.'
    inside = probes._embedded(ip)
    for net in _block_nets():
        if any(i.version == net.version and i in net for i in (ip, inside)):
            return f'Refused: {ip} is in OUTBOUND_BLOCK_NETS.'
    return None


def _check(sock):
    try:
        addr = sock.getpeername()[0]
    except (OSError, IndexError, TypeError):
        return sock   # not an IP socket (a test double): nothing to check
    why = refused(addr)
    if why:
        sock.close()
        raise Refused(why)
    return sock


class GuardedHTTPConnection(connection.HTTPConnection):
    def _new_conn(self):
        # Checked before anything is sent, TLS handshake included.
        return _check(super()._new_conn())


class GuardedHTTPSConnection(connection.HTTPSConnection):
    def _new_conn(self):
        return _check(super()._new_conn())


def install():
    connectionpool.HTTPConnectionPool.ConnectionCls = GuardedHTTPConnection
    connectionpool.HTTPSConnectionPool.ConnectionCls = GuardedHTTPSConnection
