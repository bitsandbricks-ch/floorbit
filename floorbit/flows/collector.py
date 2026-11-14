"""The flow collector: a UDP listener for NetFlow v5/v9 and IPFIX.

Run as ``python -m floorbit.flows`` (the ``flows`` service in docker-compose.yml). It reads the
same state volume as the app for the seat addresses, keeps raw flows for ``FLOWS_RETENTION_DAYS``
and publishes a summary to Redis every few seconds.
"""
import socket
import time

from integrations import config

from . import seat_maps, store
from .aggregate import Aggregator
from .parse import ParseError, Templates, parse

PUBLISH_EVERY = 10
SEATS_EVERY = 60
PRUNE_EVERY = 3600
FEATURE_EVERY = 30


class Collector:
    def __init__(self, aggregator=None, raw=None, log=print):
        self.agg = aggregator or Aggregator()
        self.raw = raw or store.RawStore()
        self.templates = Templates()
        self.log = log
        self.errors = 0
        self._next = {'publish': 0, 'seats': 0, 'prune': 0, 'feature': 0}
        self._pending = []
        self._on = True

    def enabled(self, now=None):
        """Is Traffic switched on (Settings > Features)? Asked every half minute, not per packet."""
        now = time.time() if now is None else now
        if now >= self._next['feature']:
            self._next['feature'] = now + FEATURE_EVERY
            from .. import features
            try:
                self._on = features.on('traffic')
            except (OSError, ValueError) as exc:
                self.log(f'[flows] could not read the feature switches: {exc}')
        return self._on

    def receive(self, data, exporter, now=None):
        now = time.time() if now is None else now
        try:
            flows = parse(data, exporter, self.templates)
        except (ParseError, ValueError, IndexError) as exc:
            self.errors += 1
            if self.errors <= 5 or self.errors % 1000 == 0:
                self.log(f'[flows] could not read a packet from {exporter}: {exc}')
            return 0
        self.agg.add(flows, now=now, exporter=exporter)
        self._pending += flows
        return len(flows)

    def housekeeping(self, now=None, refresh_seats=None):
        now = time.time() if now is None else now
        if now >= self._next['seats']:
            self._next['seats'] = now + SEATS_EVERY
            try:
                self.agg.set_seats(*(refresh_seats or seat_maps)())
            except Exception as exc:  # noqa: BLE001  # keep counting with the old map
                self.log(f'[flows] could not read the seat addresses: {exc}')
        pending, self._pending = self._pending, []
        try:
            self.raw.write(pending, now=now)
            self.raw.append_hours(self.agg.take_closed_hours())
            if now >= self._next['prune']:
                self._next['prune'] = now + PRUNE_EVERY
                self.raw.prune(now=now)
        except OSError as exc:
            self.log(f'[flows] could not write to {self.raw.root}: {exc}')
        if now >= self._next['publish']:
            self._next['publish'] = now + PUBLISH_EVERY
            snap = self.agg.snapshot(now=now)
            snap['raw'] = self.raw.usage()
            snap['templates_missing'] = self.templates.missing
            snap['errors'] = self.errors
            store.publish(snap)

    def serve(self, host='0.0.0.0', port=2055):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
        sock.settimeout(1.0)
        self.log(f'[flows] listening for NetFlow and IPFIX on udp/{port}')
        while True:
            try:
                data, (addr, _p) = sock.recvfrom(65535)
                if self.enabled():   # switched off: packets are read and dropped, nothing is kept
                    self.receive(data, addr)
            except TimeoutError:
                pass
            self.housekeeping()


def main():
    from .. import cache, create_app
    app = create_app(start_background=False)
    with app.app_context():
        cache.connect()
        if not cache.get_redis_client():
            print('[flows] needs Redis (REDIS_HOST) to hand the numbers to Floorbit')
        Collector().serve(port=config.get_int('FLOWS_PORT', 2055, minimum=1))
