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

**Asking DNS itself** (``Resolver``): a plugin that reports the lookup but not its answer (Pi-hole)
still says which name a seat asked for. The agent then looks the same name up through its own
resolver, usually the hall's, which mostly hands out the same cached addresses the seat just got. It
does so only for names whose site an application lists, and once per name per ``RESOLVED_TTL``. On a
timer it also resolves the sites themselves and the host names of game servers, so a flow to those
addresses is named even when no DNS plugin runs at all.
"""
import collections
import ipaddress
import socket
import threading
import time

FLOOR = 120          # seconds: a 30-second TTL still covers the download it was asked for
CAP = 1800           # seconds: a day-long TTL would keep naming an address the CDN has given to others
MAX_PAIRS = 200_000  # (seat, address) pairs; a busy hall makes a few thousand a minute
MAX_ADDRESSES = 100_000
MAX_ANSWERS = 16     # addresses kept from one answer
RESOLVED_TTL = 300   # seconds an answer of our own counts: getaddrinfo gives no TTL
REFRESH_EVERY = 600  # seconds between two rounds over the sites and hosts
MAX_QUEUE = 2_000    # names waiting to be resolved; a busy minute of new names is a few hundred
MAX_NAMES = 50_000   # names remembered with their answer
MAX_REFRESH = 1_000  # names one round resolves: the built-in lists alone can hold hundreds
PAUSE = 0.02         # seconds between two lookups of a round: at most 50 a second to the resolver


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
        seat = _address(client)   # None: the agent asked itself, so the answer is only address-wide
        if not site or (client and not seat):
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
                if seat and len(self.pairs) < MAX_PAIRS:
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


def learn_rows(rows, table=None, now=None, resolver=None):
    """``dns_queries`` rows as a DNS plugin returns them, before they are made safe to send. A row
    without answers goes to the resolver, which asks DNS itself."""
    from ..dns import site as site_of_name
    if table is None:
        table, resolver = TABLE, resolver or RESOLVER
    added = 0
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get('blocked'):
            continue
        if not row.get('answers'):
            if resolver is not None:
                resolver.ask(row.get('client'), row.get('domain'), now=now)
            continue
        site = site_of_name(row.get('domain'))
        if site:
            # From when it was asked, not when the agent read it: the feed is read once a minute.
            at = row.get('ts') if isinstance(row.get('ts'), (int, float)) else now
            added += table.learn(row.get('client'), site, row.get('answers'), now=at)
    return added


def _resolve(name):
    """The addresses ``name`` has, through the agent's own resolver."""
    infos = socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})[:MAX_ANSWERS]


class Resolver:
    """Asks DNS itself, for the lookups that came without answers and for the sites and hosts the
    rules name. One worker thread, so a slow resolver holds up nothing but itself."""

    def __init__(self, table=None, resolve=_resolve, clock=time.time, pause=PAUSE):
        self.table = table or TABLE
        self.resolve = resolve
        self.clock = clock
        self.pause = pause
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._queue = collections.OrderedDict()   # name -> set of seats that asked
        self.sites = frozenset()                  # sites an application lists: only these are resolved
        self.hosts = frozenset()                  # exact host names the rules name (game servers)
        self.answers = {}                         # name -> (addresses, until)
        self.version = 0                          # goes up when a host's addresses change
        self.resolved = self.failed = 0
        self._next_round = 0
        self._thread = None

    def want(self, sites=(), hosts=()):
        """What the rules name: lookups for these sites get resolved, and a round resolves each."""
        sites, hosts = frozenset(sites), frozenset(h.lower().rstrip('.') for h in hosts)
        with self._lock:
            if sites != self.sites or hosts != self.hosts:
                self.sites, self.hosts = sites, hosts
                self._next_round = 0
        if sites or hosts:
            self.start()
            self._wake.set()

    def want_rules(self, rules):
        sites, hosts = set(), set()
        for rule in rules or []:
            sites |= set(rule.get('sites') or ())
            hosts |= set(rule.get('hosts') or ())
        self.want(sites, hosts)

    def ask(self, client, name, now=None):
        """A seat looked ``name`` up and the plugin didn't say what it got."""
        from ..dns import site as site_of_name
        name = str(name or '').strip().lower().rstrip('.')
        site = site_of_name(name)
        if not site or site not in self.sites:
            return False
        now = self.clock() if now is None else now
        seat = _address(client)
        with self._lock:
            known = self.answers.get(name)
            if known is None or known[1] < now:
                if name not in self._queue and len(self._queue) >= MAX_QUEUE:
                    return False
                self._queue.setdefault(name, set()).update({seat} if seat else set())
                self._wake.set()
                return True
        # Answered a moment ago: the seat most likely got the same addresses.
        self.table.learn(seat, site, [{'address': a, 'ttl': known[1] - now} for a in known[0]], now=now)
        return True

    def addresses_of(self, host):
        known = self.answers.get(host)
        return known[0] if known else ()

    def start(self):
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._run, name='flow-names-resolver', daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            self._wake.wait(timeout=30)
            self._wake.clear()
            try:
                self.work()
            except Exception as exc:  # noqa: BLE001  # naming flows is extra; never let the thread die
                print(f'[flows] the names resolver stumbled: {exc}')

    def work(self, now=None):
        """Resolve what waits, then a round over the sites and hosts when one is due."""
        while True:
            with self._lock:
                if not self._queue:
                    break
                name, seats = self._queue.popitem(last=False)
            self._one(name, seats)
        now = self.clock() if now is None else now
        with self._lock:
            if now < self._next_round:
                return
            self._next_round = now + REFRESH_EVERY
            names = sorted(self.hosts) + sorted(self.sites - self.hosts)
        for name in names[:MAX_REFRESH]:
            self._one(name, ())
            if self.pause:
                time.sleep(self.pause)

    def _one(self, name, seats):
        from ..dns import site as site_of_name
        try:
            found = [a for a in (_address(x) for x in self.resolve(name)) if a]
        except (OSError, UnicodeError):
            self.failed += 1
            return
        self.resolved += 1
        now = self.clock()
        with self._lock:
            before = self.answers.get(name)
            if len(self.answers) >= MAX_NAMES:
                self.answers = {k: v for k, v in self.answers.items() if v[1] >= now}
            self.answers[name] = (tuple(found), now + RESOLVED_TTL)
            if name in self.hosts and (before is None or before[0] != tuple(found)):
                self.version += 1
        site = site_of_name(name)
        if not site or not found:
            return
        answers = [{'address': a, 'ttl': RESOLVED_TTL} for a in found]
        for seat in seats or (None,):
            self.table.learn(seat, site, answers, now=now)

    def status(self):
        return {'waiting': len(self._queue), 'names': len(self.answers), 'resolved': self.resolved,
                'failed': self.failed, 'sites': len(self.sites), 'hosts': len(self.hosts)}


# The agent's one resolver, next to its one table.
RESOLVER = Resolver(TABLE)
