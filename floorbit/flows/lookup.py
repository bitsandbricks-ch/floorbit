"""The flow lookup (#1481, C): searching the raw flows on the agent, for an incident.

The everyday Traffic pages stay hall-wide. When the crew looks into something (a P2P flood, a
DDoS-like burst, a seat that answers DHCP), someone with ``traffic.investigate`` searches the raw
flows the agent keeps for ``FLOWS_RETENTION_DAYS`` by seat, address, owner, port and time. Floorbit
asks the agent (the netflow-relay plugin's ``lookup`` call), shows what it answers, keeps nothing,
and writes every search with its reason to the audit log (floorbit/blueprints/flow_lookup.py).

This module is the agent's half: it reads ``raw/*.jsonl.gz`` and the minutes not yet written, and
answers at most ``LIMIT`` rows, newest first, with the totals of everything that matched.
"""
import calendar
import contextlib
import gzip
import heapq
import ipaddress
import itertools
import os
import time

from .classify import PROTOS
from .store import RAW_FIELDS, read_rows

LIMIT = 500           # rows sent back; the totals count every match
BUDGET = 10.0         # seconds of reading: the hosted side waits 15 for the answer
MAX_WINDOW = 8 * 86400
PEERS_MAX = 10_000
PROTO_NAMES = {v: k for k, v in PROTOS.items()}


class QueryError(ValueError):
    """A question the lookup won't answer; ``message`` is ours to show, never an exception's text."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _addresses(values):
    out = set()
    for v in values or []:
        try:
            out.add(str(ipaddress.ip_address(str(v))))
        except ValueError as exc:
            raise QueryError(f'"{v}" is not an address') from exc
    return out


def _networks(values):
    out = []
    for v in values or []:
        try:
            out.append(ipaddress.ip_network(str(v), strict=False))
        except ValueError as exc:
            raise QueryError(f'"{v}" is not an address or network') from exc
    return out


def parse_ports(text):
    """``udp/6881-6889``, ``tcp/443``, ``443`` (either protocol) or empty: [(proto or None, lo, hi)]."""
    out = []
    for spec in str(text or '').replace(',', ' ').split():
        proto, _, rng = spec.lower().rpartition('/')
        if proto and proto not in PROTOS:
            raise QueryError(f'Port "{spec}" should look like udp/6881, tcp/443 or 443-450')
        lo, _, hi = rng.partition('-')
        try:
            lo, hi = int(lo), int(hi or lo)
        except ValueError as exc:
            raise QueryError(f'Port "{spec}" should look like udp/6881, tcp/443 or 443-450') from exc
        if not (0 <= lo <= hi <= 65535):
            raise QueryError(f'Port "{spec}" should look like udp/6881, tcp/443 or 443-450')
        out.append((PROTOS.get(proto), lo, hi))
    return out


class Query:
    """What the hosted side asks: ``{since, until, sources, destination, asn, ports}``."""

    def __init__(self, args, now=None):
        now = time.time() if now is None else now
        try:
            self.until = float(args.get('until') or now)
            self.since = float(args.get('since') or self.until - 3600)
        except (TypeError, ValueError) as exc:
            raise QueryError('since and until are unix times') from exc
        if self.since >= self.until:
            raise QueryError('since must be before until')
        if self.until - self.since > MAX_WINDOW:
            raise QueryError('Search at most 8 days at a time')
        self.sources = _addresses(args.get('sources'))
        self.destinations = _networks(args.get('destination'))
        try:
            self.asn = int(args['asn']) if args.get('asn') not in (None, '') else None
        except (TypeError, ValueError) as exc:
            raise QueryError('asn is a number') from exc
        self.ports = parse_ports(args.get('ports'))
        try:
            self.limit = max(1, min(LIMIT, int(args.get('limit') or LIMIT)))
        except (TypeError, ValueError):
            self.limit = LIMIT
        if not (self.sources or self.destinations or self.asn is not None or self.ports):
            raise QueryError('Name a seat, an address, an owner or a port: not the whole hall')

    def matches(self, row, owner_of):
        # A row's minute starts up to 60 s before the flow it holds.
        if not (self.since - 60 < row['t'] <= self.until):
            return False
        src, dst = row['src'], row['dst']
        if self.sources:
            if src in self.sources:
                remotes = (dst,)
            elif dst in self.sources:
                remotes = (src,)
            else:
                return False
        else:
            remotes = (src, dst)
        if self.destinations and not any(_in(r, self.destinations) for r in remotes):
            return False
        if self.asn is not None and not any((owner_of(r) or (None,))[0] == self.asn for r in remotes):
            return False
        return not self.ports or any(
            (p is None or p == row['proto']) and (lo <= row['sport'] <= hi or lo <= row['dport'] <= hi)
            for p, lo, hi in self.ports)


def _in(address, nets):
    try:
        addr = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(addr.version == n.version and addr in n for n in nets)


def _files(raw_dir, since, until):
    if not os.path.isdir(raw_dir):
        return []
    out = []
    for name in os.listdir(raw_dir):
        if not name.endswith('.jsonl.gz'):
            continue
        try:
            start = calendar.timegm(time.strptime(name[:13], '%Y-%m-%d-%H'))
        except ValueError:
            continue
        if start + 3600 > since - 60 and start <= until:
            out.append((start, os.path.join(raw_dir, name)))
    return [p for _, p in sorted(out, reverse=True)]


def _matching(raw_dir, q, pending, owner_of, clock, started):
    """Every row that matches, the minutes not yet on disk first, then the files newest first. Stops
    after ``BUDGET`` seconds; the caller learns it from ``stopped``."""
    state = {'stopped': False}

    def rows():
        for key, (b, p, r) in list((pending or {}).items()):
            row = dict(zip(RAW_FIELDS, (*key, b, p, r), strict=True))
            if q.matches(row, owner_of):
                yield row
        for path in _files(raw_dir, q.since, q.until):
            if clock() - started > BUDGET:
                state['stopped'] = True
                return
            try:
                with gzip.open(path, 'rt', encoding='utf-8') as f:
                    for n, row in enumerate(read_rows(f)):
                        if q.matches(row, owner_of):
                            yield row
                        if n % 50_000 == 0 and clock() - started > BUDGET:
                            state['stopped'] = True
                            return
            except (OSError, EOFError):
                continue   # a file being written or cut short: the rest still answers

    return rows(), state


def search(raw_dir, args, pending=None, classify=None, owner_of=None, now=None, clock=time.monotonic):
    """Answer one lookup. ``pending``: the merged rows not yet on disk ({key: [bytes, packets,
    records]}, collector.py). ``classify``/``owner_of``: the collector's, to name each row."""
    q = Query(args, now=now)
    owner_of = owner_of or (lambda ip: None)
    found, total, size, peers = [], 0, 0, set()
    order = itertools.count()
    rows, state = _matching(raw_dir, q, pending, owner_of, clock, clock())
    for row in rows:
        total += 1
        size += row['bytes']
        if q.sources:
            remote = row['dst'] if row['src'] in q.sources else row['src']
            if len(peers) < PEERS_MAX:
                peers.add(remote)
        item = (row['t'], row['bytes'], next(order), row)
        # Only the newest ``limit`` stay in memory: a week of a busy seat can match millions.
        if len(found) < q.limit:
            heapq.heappush(found, item)
        elif item > found[0]:
            heapq.heapreplace(found, item)
    rows = [_named(item[3], q, classify, owner_of) for item in sorted(found, reverse=True)]
    return {'rows': rows, 'total': total, 'bytes': size, 'peers': len(peers) if q.sources else None,
            'stopped': state['stopped'], 'oldest': _oldest(raw_dir)}


SUMMARY_TOP = 5


def summary(raw_dir, args, pending=None, classify=None, owner_of=None, now=None, clock=time.monotonic):
    """One seat's traffic for the seat panel (#1481, B): its volume, its categories, its top
    applications and the networks' owners it talked to. Totals only: never a name it looked up,
    never a single remote address."""
    if not (args or {}).get('sources'):
        raise QueryError('Name the seat')
    q = Query({k: args.get(k) for k in ('since', 'until', 'sources')}, now=now)
    owner_of = owner_of or (lambda ip: None)
    size = 0
    categories, apps, owners = {}, {}, {}
    rows, state = _matching(raw_dir, q, pending, owner_of, clock, clock())
    for row in rows:
        size += row['bytes']
        if row['dst'] in q.sources:
            remote, remote_port, local_port = row['src'], row['sport'], row['dport']
        else:
            remote, remote_port, local_port = row['dst'], row['dport'], row['sport']
        name, category = 'Other', 'other'
        if classify is not None:
            with contextlib.suppress(Exception):   # a name is extra; the bytes still count
                name, category = classify(remote, row['proto'], remote_port, local_port)
        categories[category] = categories.get(category, 0) + row['bytes']
        app = apps.setdefault(name, [category, 0])
        app[1] += row['bytes']
        owner = owner_of(remote)
        if owner:
            entry = owners.setdefault(owner[0], [owner[1], 0])
            entry[1] += row['bytes']
    top_apps = sorted(apps.items(), key=lambda kv: -kv[1][1])[:SUMMARY_TOP]
    top_owners = sorted(owners.items(), key=lambda kv: -kv[1][1])[:SUMMARY_TOP]
    return {'bytes': size, 'categories': categories,
            'applications': [{'name': n, 'category': c, 'bytes': b} for n, (c, b) in top_apps],
            'owners': [{'asn': a, 'name': n, 'bytes': b} for a, (n, b) in top_owners],
            'stopped': state['stopped'], 'oldest': _oldest(raw_dir)}


def _named(row, q, classify, owner_of):
    out = {k: row[k] for k in ('t', 'src', 'dst', 'proto', 'sport', 'dport', 'bytes', 'packets')}
    out['protocol'] = PROTO_NAMES.get(row['proto'], str(row['proto']))
    # The remote side: the one that isn't the searched seat, else the destination.
    if q.sources and row['dst'] in q.sources:
        remote, remote_port, local_port = row['src'], row['sport'], row['dport']
    else:
        remote, remote_port, local_port = row['dst'], row['dport'], row['sport']
    owner = owner_of(remote)
    out['owner'] = {'asn': owner[0], 'name': owner[1]} if owner else None
    if classify is not None:
        try:
            out['application'] = classify(remote, row['proto'], remote_port, local_port)[0]
        except Exception:  # noqa: BLE001  # a name is extra; the row still answers
            out['application'] = None
    return out


def _oldest(raw_dir):
    files = _files(raw_dir, 0, float('inf'))
    return os.path.basename(files[-1])[:13] if files else None
