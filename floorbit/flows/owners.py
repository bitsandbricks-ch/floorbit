"""Who a remote address belongs to: its network (AS) and owner, for the Traffic page (issue #1481, A2).

The list is iptoasn.com's ``ip2asn-combined.tsv.gz`` (public domain, PDDL 1.0): one line per range,
``range_start range_end AS_number country AS_description``. Whoever runs the flow collector (the
local agent) fetches it once a day into ``FLOWS_DIR`` and looks addresses up in memory. Only the
owner's name and number leave the agent, under the same five-seat rule as applications.
"""
import bisect
import gzip
import ipaddress
import os
import threading
import time

URL = 'https://iptoasn.com/data/ip2asn-combined.tsv.gz'
FILE = 'ip2asn-combined.tsv.gz'
REFRESH = 24 * 3600
RETRY = 3600            # after a failed fetch
MAX_BYTES = 64 * 1024 ** 2
TIMEOUT = 60
CACHE = 100_000         # remote addresses remembered between lookups
NAME_MAX = 80


def _name(description):
    """iptoasn's description is "SHORT-NAME - Long name" or just a name; keep the readable part."""
    text = ' '.join(str(description).split())
    short, sep, long = text.partition(' - ')
    return (long if sep and long else short)[:NAME_MAX] or None


class Table:
    """Sorted ranges per address family, looked up with bisect. Neighbouring ranges of one AS are
    merged while loading: the file splits them by announcement, which nobody here cares about."""

    def __init__(self):
        self.starts = {4: [], 6: []}
        self.ends = {4: [], 6: []}
        self.asns = {4: [], 6: []}
        self.names = {}

    @classmethod
    def read(cls, lines):
        table = cls()
        rows = {4: [], 6: []}
        for line in lines:
            parts = line.rstrip('\n').split('\t')
            if len(parts) < 5:
                continue
            try:
                lo, hi, asn = ipaddress.ip_address(parts[0]), ipaddress.ip_address(parts[1]), int(parts[2])
            except ValueError:
                continue
            if asn <= 0 or lo.version != hi.version or int(hi) < int(lo):
                continue    # AS 0: not routed
            rows[lo.version].append((int(lo), int(hi), asn))
            if asn not in table.names:
                table.names[asn] = _name(parts[4])
        for family, found in rows.items():
            found.sort()
            starts, ends, asns = table.starts[family], table.ends[family], table.asns[family]
            for lo, hi, asn in found:
                if asns and asns[-1] == asn and lo <= ends[-1] + 1:
                    ends[-1] = max(ends[-1], hi)
                    continue
                starts.append(lo)
                ends.append(hi)
                asns.append(asn)
        return table

    def __len__(self):
        return len(self.starts[4]) + len(self.starts[6])

    def lookup(self, address):
        """(AS number, owner name) for a public address, or None."""
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return None
        if not ip.is_global:
            return None
        family, value = ip.version, int(ip)
        i = bisect.bisect_right(self.starts[family], value) - 1
        if i < 0 or value > self.ends[family][i]:
            return None
        asn = self.asns[family][i]
        return asn, self.names.get(asn) or f'AS{asn}'


class Owners:
    """The table and keeping it current. ``lookup`` answers None until a list is loaded."""

    def __init__(self, folder=None, fetch=None, log=print):
        self._folder = folder
        self._fetch = fetch or _download
        self.log = log
        self.table = None
        self.updated = None     # when the loaded list was fetched
        self._cache = {}
        self._busy = threading.Lock()
        self._next_try = 0

    def folder(self):
        if self._folder:
            return self._folder
        from .store import flows_dir
        return flows_dir()

    def path(self):
        return os.path.join(self.folder(), FILE)

    def lookup(self, address):
        if self.table is None:
            return None
        found = self._cache.get(address, False)
        if found is False:
            found = self.table.lookup(address)
            if len(self._cache) >= CACHE:
                self._cache.clear()
            self._cache[address] = found
        return found

    def status(self):
        return {'updated': self.updated, 'ranges': len(self.table) if self.table else 0} if self.table else None

    def refresh(self, now=None, wait=False):
        """Fetch when the list on disk is a day old (or missing), and load it when it is newer than
        the one in memory. Runs in its own thread unless ``wait``: the file is a few MB."""
        now = time.time() if now is None else now
        if now < self._next_try or not self._busy.acquire(blocking=False):
            return
        self._next_try = now + RETRY
        if wait:
            self._refresh(now)
        else:
            threading.Thread(target=self._refresh, args=(now,), name='flow-owners', daemon=True).start()

    def _refresh(self, now):
        try:
            path = self.path()
            try:
                fetched = os.path.getmtime(path)
            except OSError:
                fetched = None
            if fetched is None or now - fetched >= REFRESH:
                try:
                    os.makedirs(self.folder(), exist_ok=True)
                    self._fetch(path)
                    fetched = os.path.getmtime(path)
                    self._next_try = now + REFRESH
                except Exception as exc:  # noqa: BLE001  # keep the old list; try again in an hour
                    self.log(f'[flows] could not fetch the network owner list: {exc}')
            if fetched is not None and fetched != self.updated:
                with gzip.open(path, 'rt', encoding='utf-8', errors='replace') as fh:
                    table = Table.read(fh)
                self.table, self.updated, self._cache = table, fetched, {}
                if self._next_try < fetched + REFRESH:
                    self._next_try = fetched + REFRESH
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            self.log(f'[flows] could not read the network owner list: {exc}')
        finally:
            self._busy.release()


def _download(path):
    import requests
    part = path + '.part'
    got = 0
    with requests.get(URL, stream=True, timeout=TIMEOUT) as answer:
        answer.raise_for_status()
        with open(part, 'wb') as fh:
            for chunk in answer.iter_content(1 << 16):
                got += len(chunk)
                if got > MAX_BYTES:
                    raise ValueError('the owner list is larger than expected')
                fh.write(chunk)
    with gzip.open(part, 'rt', encoding='utf-8', errors='replace') as fh:
        if not fh.readline().count('\t') >= 4:
            raise ValueError('the owner list is not in the expected format')
    os.replace(part, path)
