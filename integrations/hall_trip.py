"""Check-in opened on Floorbit's own address goes on to the hall (issue #1177).

Only a local agent's front door sees a seat PC's own address, so a check-in on Floorbit's main
address keeps the seat but can't learn its switch port. A PC at its seat is on the event network,
so its page sends it on to an agent's front door (``seat_walk.agent_url``: the check-in name, else
where browsers last reached an agent), where the same check-in page then knows the PC.

A browser off the event network can't open that address, and a page can't test it first (an HTTPS
page may not even ask an HTTP one), so the page only goes on by itself where Floorbit is sure: the
browser comes from an address a trip to a front door already worked from, or the one a connected
agent comes from. Everyone else gets a button and can still check in where they are.

The trip carries a one-time code (``via``) minted for the browser's address as Floorbit saw it;
when the code arrives through a front door, that address is known to be the hall's. Only public
addresses count: behind a proxy Floorbit doesn't trust, every browser has the proxy's private one.
"""

import ipaddress
import re
import secrets
import threading
import time

TRIP_SECONDS = 10 * 60          # a code is good this long
KEEP_SECONDS = 7 * 24 * 3600     # an address a trip worked from counts this long (an event's length)
MAX_TRIPS = 2000                 # codes waiting at once; one per page view from outside
MAX_ADDRESSES = 200              # an event has a few uplinks, not hundreds
TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{16,64}\Z')
_lock = threading.Lock()


def _path():
    from floorbit import store
    return store.event_path('checkin_hall_trips.json')


def _load(now):
    """``{"trips": {code: {at, from}}, "hall": {address: last worked}}`` without the old ones. A
    document, so every pod sees a trip another pod started."""
    from floorbit import store
    doc = store.read_json(_path(), {}) or {}
    trips = {t: r for t, r in (doc.get('trips') or {}).items()
             if isinstance(r, dict) and now - (r.get('at') or 0) < TRIP_SECONDS}
    hall = {a: at for a, at in (doc.get('hall') or {}).items()
            if isinstance(at, (int, float)) and now - at < KEEP_SECONDS}
    return {'trips': trips, 'hall': hall}


def _save(doc):
    from floorbit import store
    store.write_json(_path(), doc)


# Where a proxy, a pod network or a LAN hands out addresses: one of these names many browsers.
_LOCAL = [ipaddress.ip_network(n) for n in (
    '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16',
    '0.0.0.0/8', 'fc00::/7', 'fe80::/10', '::1/128', '::/128')]


def public(ip):
    """``ip`` when it names a site on the internet (the hall's uplink), else None."""
    try:
        addr = ipaddress.ip_address(str(ip or '').strip())
    except ValueError:
        return None
    if getattr(addr, 'ipv4_mapped', None):
        addr = addr.ipv4_mapped
    return None if any(addr in n for n in _LOCAL if n.version == addr.version) else str(addr)


def _agent_addresses():
    """Where connected agents reach Floorbit from: behind the hall's NAT, the hall's address too."""
    from floorbit import agent_link
    try:
        return {public(a.get('address')) for a in agent_link.all_agents() if a.get('connected')} - {None}
    except Exception as exc:  # noqa: BLE001  # no agents: no address to be sure of
        print(f'[checkin] could not read the agents: {exc}')
        return set()


def start(client, now=None):
    """A code for this browser's trip to the hall; ``client`` is its address as Floorbit sees it."""
    now = time.time() if now is None else now
    token = secrets.token_urlsafe(18)
    with _lock:
        doc = _load(now)
        if len(doc['trips']) >= MAX_TRIPS:
            # Full of codes nobody took: drop the oldest rather than leave the newest browser without one.
            for old in sorted(doc['trips'], key=lambda t: doc['trips'][t].get('at') or 0)[:len(doc['trips']) // 2]:
                doc['trips'].pop(old)
        doc['trips'][token] = {'at': now, 'from': public(client)}
        _save(doc)
    return token


def arrived(token, now=None):
    """The code came through a front door: the address it was minted for is the hall's. False for an
    unknown or used code."""
    now = time.time() if now is None else now
    if not TOKEN_RE.match(str(token or '')):
        return False
    with _lock:
        doc = _load(now)
        row = doc['trips'].pop(token, None)
        if row is None:
            return False
        if row.get('from'):
            doc['hall'][row['from']] = now
            if len(doc['hall']) > MAX_ADDRESSES:
                for old in sorted(doc['hall'], key=doc['hall'].get)[:len(doc['hall']) - MAX_ADDRESSES]:
                    doc['hall'].pop(old)
        _save(doc)
    return True


def sure(client, now=None):
    """Is a browser at ``client`` on the event network, as far as Floorbit can tell?"""
    addr = public(client)
    if not addr:
        return False
    now = time.time() if now is None else now
    return addr in _load(now)['hall'] or addr in _agent_addresses()
