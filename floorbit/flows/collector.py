"""The flow collector: NetFlow v5/v9 and IPFIX, counted on the local agent.

The agent's netflow-relay plugin feeds it the packets it receives on the plugin's port, gives it
the seat addresses and sends the summary it makes every few seconds to Floorbit. The raw flows stay
on the agent for ``FLOWS_RETENTION_DAYS``.
"""
import ipaddress
import threading
import time

from integrations import config

from . import seat_maps, store
from .aggregate import Aggregator
from .parse import ParseError, Templates, parse

PUBLISH_EVERY = 10
SEATS_EVERY = 60
PRUNE_EVERY = 3600
FEATURE_EVERY = 30
ALLOW_EVERY = 30
RAW_EVERY = 5         # seconds between raw writes: one gzip member per packet cost more than the rest
MAX_PENDING = 500_000  # raw flows waiting for the disk; past that the oldest go unwritten (counted)


class Collector:
    def __init__(self, aggregator=None, raw=None, log=print):
        self.agg = aggregator or Aggregator()
        self.raw = raw or store.RawStore()
        self.templates = Templates()
        self.log = log
        self.errors = 0
        self.refused = 0
        self._allow = (None, None)     # (monotonic time read, networks or None for everyone)
        self._next = {'publish': 0, 'seats': 0, 'prune': 0, 'feature': 0, 'raw': 0}
        self._pending = []
        self._lock = threading.Lock()   # receive() and housekeeping() may run in two threads
        self.raw_skipped = 0
        self._on = True
        self.publish = lambda snap: False   # the agent sets where the summary goes

    def _due(self, name, now, every):
        """Time for this chore again? Also when the clock was set back past its schedule, else
        publishing stopped until the clock caught up."""
        if now >= self._next[name] or self._next[name] - now > every:
            self._next[name] = now + every
            return True
        return False

    def enabled(self, now=None):
        """Is Traffic switched on (Settings > Features)? Asked every half minute, not per packet."""
        now = time.time() if now is None else now
        if self._due('feature', now, FEATURE_EVERY):
            from .. import features
            try:
                self._on = features.on('traffic')
            except (OSError, ValueError) as exc:
                self.log(f'[flows] could not read the feature switches: {exc}')
        return self._on

    def _networks(self):
        """The ``FLOWS_ALLOW`` networks, or None when it is empty (everyone may send, as before)."""
        at, nets = self._allow
        if at is not None and time.monotonic() - at < ALLOW_EVERY:
            return nets
        entries = [e.strip() for e in (config.get('FLOWS_ALLOW') or '').split(',') if e.strip()]
        nets = []
        for entry in entries:
            try:
                nets.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                self.log(f'[flows] FLOWS_ALLOW: {entry!r} is not an address or network, left out')
        # Only typos: refuse everyone rather than quietly let everyone in.
        self._allow = (time.monotonic(), nets if entries else None)
        return self._allow[1]

    def exporter_ok(self, exporter):
        nets = self._networks()
        if nets is None:
            return True
        try:
            ip = ipaddress.ip_address(str(exporter).split('%')[0])
        except ValueError:
            return False
        return any(ip in net for net in nets)

    def receive(self, data, exporter, now=None):
        now = time.time() if now is None else now
        # Anyone on the event network can send UDP here; a forged packet would add made-up
        # traffic to a seat, so with FLOWS_ALLOW set only those exporters count.
        if not self.exporter_ok(exporter):
            self.refused += 1
            if self.refused <= 5 or self.refused % 1000 == 0:
                self.log(f'[flows] refused a packet from {exporter}: not in FLOWS_ALLOW ({self.refused} so far)')
            return 0
        try:
            flows = parse(data, exporter, self.templates)
        except (ParseError, ValueError, IndexError) as exc:
            self.errors += 1
            if self.errors <= 5 or self.errors % 1000 == 0:
                self.log(f'[flows] could not read a packet from {exporter}: {exc}')
            return 0
        with self._lock:
            self.agg.add(flows, now=now, exporter=exporter)
            self._pending += flows
            if len(self._pending) > MAX_PENDING:
                over = len(self._pending) - MAX_PENDING
                del self._pending[:over]
                self.raw_skipped += over
        return len(flows)

    def housekeeping(self, now=None, refresh_seats=None):
        now = time.time() if now is None else now
        if self._due('seats', now, SEATS_EVERY):
            try:
                seat_of = (refresh_seats or seat_maps)()
                with self._lock:
                    self.agg.set_seats(*seat_of)
            except Exception as exc:  # noqa: BLE001  # keep counting with the old map
                self.log(f'[flows] could not read the seat addresses: {exc}')
        # Only the hand-over holds the lock: the disk and the network are slow, packets aren't.
        pending, hours, snap = [], [], None
        with self._lock:
            if self._due('raw', now, RAW_EVERY):
                pending, self._pending = self._pending, []
                hours = self.agg.take_closed_hours()
            if self._due('publish', now, PUBLISH_EVERY):
                snap = self.agg.snapshot(now=now)
        try:
            self.raw.write(pending, now=now)
            self.raw.append_hours(hours)
            if self._due('prune', now, PRUNE_EVERY):
                self.raw.prune(now=now)
        except OSError as exc:
            self.log(f'[flows] could not write to {self.raw.root}: {exc}')
        if snap is not None:
            snap['raw'] = self.raw.usage()
            snap['templates_missing'] = self.templates.missing
            snap['errors'] = self.errors
            snap['refused'] = self.refused
            snap['raw_skipped'] = self.raw_skipped
            self.publish(snap)
