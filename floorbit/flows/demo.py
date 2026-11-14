"""FLOORBIT_DEMO=1: made-up flows for the demo hall, fed through the real aggregation.

No collector runs in the demo: a thread in the app makes flows like the demo hall's players would
(Steam matches, the LAN cache, streams, updates, a torrent seat at D-5, the rogue DHCP server at A-7
that the security demo also shows) and hands them to an ``Aggregator`` every few seconds.
"""
import random
import threading
import time

from .aggregate import Aggregator
from .classify import BUILTIN, Classifier, compile_rules

STEP = 10
LAN_CACHE = '198.51.100.50'
DEMO_RULES = [{'name': 'LAN cache', 'category': 'downloads', 'cidr': [f'{LAN_CACHE}/32']},
              {'name': 'Tournament servers', 'category': 'gaming', 'cidr': ['198.51.100.64/28']},
              {'name': 'Video streaming', 'category': 'streaming', 'cidr': ['203.0.113.20/32']}]
REMOTE = {'web': '203.0.113.10', 'stream': '203.0.113.20', 'steam': '203.0.113.30', 'update': '203.0.113.40'}


def _flow(src, dst, sport, dport, proto, size, now):
    return {'src': src, 'dst': dst, 'sport': sport, 'dport': dport, 'proto': proto,
            'bytes': int(size), 'packets': max(1, int(size // 1200)), 'end': now}


def flows_for(now, step=STEP):
    """One step's worth of flows for every taken seat."""
    from ..builtin_plugins.demo.plugin import Plugin, _ip, _seats, _taken
    rnd = random.Random(int(now // step))
    out = []
    for seat, _block, _number, i in _seats():
        if not _taken(i):
            continue
        down, up = (r * step for r in Plugin._rates(i))
        ip = _ip(i)
        kind = i % 6
        if kind in (0, 1):      # in a match
            server = f'198.51.100.{64 + i % 8}' if kind == 0 else REMOTE['steam']
            out.append(_flow(server, ip, 27015, 50000 + i, 17, down * 0.7, now))
            out.append(_flow(ip, server, 50000 + i, 27015, 17, up, now))
        elif kind == 2:         # downloading a game from the LAN cache
            out.append(_flow(LAN_CACHE, ip, 80, 40000 + i, 6, down * 0.9, now))
        elif kind == 3:         # watching or sending a stream
            out.append(_flow(REMOTE['stream'], ip, 443, 41000 + i, 17, down * 0.8, now))
            if i % 4 == 0:
                out.append(_flow(ip, REMOTE['stream'], 42000 + i, 1935, 6, up * 3, now))
        elif kind == 4:         # updates
            out.append(_flow(REMOTE['update'], ip, 7680, 43000 + i, 6, down * 0.8, now))
        else:
            out.append(_flow(REMOTE['web'], ip, 443, 44000 + i, 6, down * 0.8, now))
        out.append(_flow(REMOTE['web'], ip, 443, 45000 + i, 6, down * 0.2, now))
        if seat == 'D-5':       # a torrent: lots of peers
            for p in range(400):
                peer = f'203.0.113.{100 + p % 150}' if p < 150 else f'198.18.{p // 250}.{p % 250}'
                out.append(_flow(ip, peer, 6881, 30000 + p, 17, 40_000 + rnd.randint(0, 20_000), now))
        if seat == 'A-7' and int(now // 60) % 6 < 3:   # the rogue DHCP server from the security demo
            out.append(_flow(ip, '255.255.255.255', 67, 68, 17, 600, now))
    return out


class DemoFlows:
    def __init__(self):
        self.agg = Aggregator(Classifier(compile_rules(DEMO_RULES) + compile_rules(BUILTIN)))
        self._stop = threading.Event()
        self._thread = None

    def seats(self):
        from ..builtin_plugins.demo.plugin import _ip, _seats
        return {_ip(i): s for s, _b, _n, i in _seats()}, {s: b for s, b, _n, _i in _seats()}

    def backfill(self, now=None, minutes=60):
        """The last hour, so the page isn't empty right after start."""
        now = time.time() if now is None else now
        self.agg.set_seats(*self.seats())
        for k in range(minutes * 60 // STEP, 0, -1):
            t = now - k * STEP
            self.agg.add(flows_for(t), now=t, exporter='198.51.100.1')

    def start(self):
        if self._thread:
            return
        self.backfill()
        self._thread = threading.Thread(target=self._run, name='demo-flows', daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.wait(STEP):
            self.agg.add(flows_for(time.time()), exporter='198.51.100.1')

    def snapshot(self):
        snap = self.agg.snapshot()
        snap['raw'] = {'files': 0, 'bytes': 0, 'oldest': None}
        snap['demo'] = True
        return snap
