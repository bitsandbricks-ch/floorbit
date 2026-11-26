"""Naming HTTPS flows by the DNS answers the seats got (#1600).

A flow record has addresses and ports, never a host name, and pfSense and Nexus exporters send no
TLS server name either. But a seat usually asks DNS before it connects: when it looks up
``cdn.example.com`` and gets ``198.51.100.7``, a flow from that seat to that address in the next
minutes is for ``example.com``. Through the applications' sites, it then counts for the launcher or
game whose site it is (floorbit/flows/classify.py).

- **Per seat first:** ``(seat address, remote address) -> site`` for the answer's TTL, at least
  ``FLOOR`` and at most ``CAP``.
- **Then address-wide:** a flow with no lookup behind it (a long download that began before the
  window, a seat that asked another resolver) takes the site last answered for that address by any
  seat, but only when exactly one site has it. A shared CDN address answers for several sites and
  names nobody.

The table only lives in the agent's memory: the pairs of seat, address and name never leave the
hall; only the totals per application go to Floorbit, under the five-seat rule (aggregate.py).

The agent fills it from the DNS plugins whose ``dns_queries`` rows carry ``answers`` (docs/dns.md);
it reads them where it reads the lookups for DNS analytics (floorbit_agent ``dns_feeds``).
"""
import ipaddress
import threading
import time

FLOOR = 120          # seconds: a 30-second TTL still covers the download it was asked for
CAP = 1800           # seconds: a day-long TTL would keep naming an address the CDN has given to others
MAX_PAIRS = 200_000  # (seat, address) pairs; a busy hall makes a few thousand a minute
MAX_ADDRESSES = 100_000
MAX_ANSWERS = 16     # addresses kept from one answer


def _address(value):
    try:
        return str(ipaddress.ip_address(str(value).split('%')[0].strip()))
    except ValueError:
        return None


class Names:
    def __init__(self):
        self._lock = threading.Lock()
        self.pairs = {}       # (seat ip, remote ip) -> (site, until)
        self.addresses = {}   # remote ip -> {site: until}
        self.learned = 0

    def learn(self, client, site, answers, now=None):
        """One lookup: ``client`` asked for ``site`` and got ``answers``, each an address or
        ``{'address', 'ttl'}``."""
        now = time.time() if now is None else now
        seat = _address(client)
        if not seat or not site:
            return 0
        added = 0
        with self._lock:
            for answer in (answers or [])[:MAX_ANSWERS]:
                if isinstance(answer, dict):
                    address, ttl = _address(answer.get('address')), answer.get('ttl')
                else:
                    address, ttl = _address(answer), None
                if not address:
                    continue
                try:
                    ttl = int(ttl)
                except (TypeError, ValueError):
                    ttl = FLOOR
                until = now + min(CAP, max(FLOOR, ttl))
                if len(self.pairs) >= MAX_PAIRS or len(self.addresses) >= MAX_ADDRESSES:
                    self._prune(now)
                if len(self.pairs) < MAX_PAIRS:
                    self.pairs[(seat, address)] = (site, until)
                if address in self.addresses or len(self.addresses) < MAX_ADDRESSES:
                    self.addresses.setdefault(address, {})[site] = until
                added += 1
            self.learned += added
        return added

    def site_of(self, seat, remote, now=None):
        """The site a flow between ``seat`` and ``remote`` is for, or None."""
        now = time.time() if now is None else now
        found = self.pairs.get((seat, remote))
        if found and found[1] >= now:
            return found[0]
        sites = self.addresses.get(remote)
        if not sites:
            return None
        live = [s for s, until in list(sites.items()) if until >= now]
        return live[0] if len(live) == 1 else None

    def _prune(self, now):
        self.pairs = {k: v for k, v in self.pairs.items() if v[1] >= now}
        kept = {}
        for address, sites in self.addresses.items():
            live = {s: u for s, u in sites.items() if u >= now}
            if live:
                kept[address] = live
        self.addresses = kept

    def prune(self, now=None):
        with self._lock:
            self._prune(time.time() if now is None else now)

    def status(self):
        return {'pairs': len(self.pairs), 'addresses': len(self.addresses), 'learned': self.learned}


# The agent's one table: the DNS feed fills it, the flow collector reads it. Both run in the agent.
TABLE = Names()


def learn_rows(rows, table=None, now=None):
    """``dns_queries`` rows as a DNS plugin returns them, before they are made safe to send."""
    from ..dns import site as site_of_name
    table = table or TABLE
    added = 0
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get('blocked') or not row.get('answers'):
            continue
        site = site_of_name(row.get('domain'))
        if site:
            # From when it was asked, not when the agent read it: the feed is read once a minute.
            at = row.get('ts') if isinstance(row.get('ts'), (int, float)) else now
            added += table.learn(row.get('client'), site, row.get('answers'), now=at)
    return added
