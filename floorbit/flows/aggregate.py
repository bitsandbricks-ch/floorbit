"""Turning flow records into aggregate numbers, and spotting what ops should look at.

Privacy (issue #25, Swiss and EU rules): nothing here keeps what a person visited.

- **Hall and areas:** bytes per category, per minute for the last hour and per hour for longer.
- **Services:** bytes per service (from ``classify.py``) and how many different seats used it. A
  service is only named once ``FLOWS_MIN_SEATS`` (5) different seats used it; below that it counts
  as "Other", so a rare service can't point at one person.
- **Per seat:** only total volume and the category mix ("80 GB, mostly gaming"). Never services,
  addresses or ports.
- **Anomalies:** P2P floods, DDoS-like bursts and seats acting as DHCP or DNS servers. They name the
  seat, like a security finding, so only ``seats.view`` sees which one.

Only flows with a seat on one side count: the seat addresses come from the seat sources.
"""
import threading
import time
from collections import defaultdict

from integrations import config

from .classify import Classifier

MINUTE, HOUR, DAY = 60, 3600, 24 * 3600
TCP, UDP = 6, 17
ANOMALY_HOLD = 10 * MINUTE     # an anomaly stays listed this long after it was last seen
PEER_CAP = 2000                # distinct peers tracked per seat and minute


def _cats():
    return defaultdict(int)


def _bucket():
    return {'total': _cats(), 'areas': defaultdict(_cats)}


def _hour():
    return {'total': _cats(), 'areas': defaultdict(_cats),
            'services': defaultdict(lambda: {'bytes': 0, 'category': 'other', 'seats': set()}),
            'seats': defaultdict(lambda: {'bytes': 0, 'mix': _cats()})}


def settings():
    return {'min_seats': config.get_int('FLOWS_MIN_SEATS', 5, minimum=2),
            'p2p_peers': config.get_int('FLOWS_P2P_PEERS', 300, minimum=10),
            'burst_pps': config.get_int('FLOWS_BURST_PPS', 50_000, minimum=100),
            'retention_days': config.get_int('FLOWS_RETENTION_DAYS', 7, minimum=1)}


class Aggregator:
    def __init__(self, classifier=None, now=None):
        self.classify = classifier or Classifier()
        self._lock = threading.Lock()
        self.seat_of = {}          # ip -> seat
        self.area_of = {}          # seat -> area (seat block name)
        self.minutes = {}          # minute start -> bucket
        self.hours = {}            # hour start -> hour
        self.anomalies = {}        # id -> anomaly
        self.flows = 0
        self.exporters = {}        # exporter ip -> {'flows', 'last'}
        self._minute = None
        self._window = self._new_window()
        self.closed_hours = []     # hours finished since the last call to take_closed_hours()

    @staticmethod
    def _new_window():
        return {'peers': defaultdict(set), 'packets_to': defaultdict(int), 'packets_from': defaultdict(int),
                'senders_to': defaultdict(set), 'dhcp': set(), 'dns': set(), 'torrent': defaultdict(int)}

    def set_seats(self, seat_of, area_of):
        with self._lock:
            self.seat_of = dict(seat_of)
            self.area_of = dict(area_of)

    # ── adding flows ──────────────────────────────────────────────────────────
    def add(self, flows, now=None, exporter=None):
        now = time.time() if now is None else now
        with self._lock:
            self._roll(now)
            minute = self.minutes.setdefault(int(now // MINUTE) * MINUTE, _bucket())
            hour = self.hours.setdefault(int(now // HOUR) * HOUR, _hour())
            if exporter:
                seen = self.exporters.setdefault(exporter, {'flows': 0, 'last': None})
                seen['flows'] += len(flows)
                seen['last'] = now
            for f in flows:
                self._add_one(f, minute, hour)

    def _add_one(self, f, minute, hour):
        src_seat, dst_seat = self.seat_of.get(f['src']), self.seat_of.get(f['dst'])
        if not src_seat and not dst_seat:
            return
        self.flows += 1
        size, w = f['bytes'], self._window
        # The seat's side decides the direction; between two seats, the receiver's view counts.
        if dst_seat:
            seat, remote, local_port, remote_port = dst_seat, f['src'], f['dport'], f['sport']
        else:
            seat, remote, local_port, remote_port = src_seat, f['dst'], f['sport'], f['dport']
        service, category = self.classify(remote, f['proto'], remote_port, local_port)
        area = self.area_of.get(seat) or 'Other'
        for bucket in (minute, hour):
            bucket['total'][category] += size
            bucket['areas'][area][category] += size
        svc = hour['services'][service]
        svc['bytes'] += size
        svc['category'] = category
        svc['seats'].add(seat)
        for s in {src_seat, dst_seat} - {None}:
            hour['seats'][s]['bytes'] += size
            hour['seats'][s]['mix'][category] += size
        # Anomaly signs, per minute.
        if src_seat:
            peers = w['peers'][src_seat]
            if len(peers) < PEER_CAP:
                peers.add(f['dst'])
            w['packets_from'][src_seat] += f['packets']
            if f['proto'] == UDP and f['sport'] == 67 and f['dport'] == 68:
                w['dhcp'].add(src_seat)
            if f['proto'] == UDP and f['sport'] == 53 and dst_seat:
                w['dns'].add(src_seat)
            if service == 'BitTorrent':
                w['torrent'][src_seat] += size
        w['packets_to'][f['dst']] += f['packets']
        if src_seat and len(w['senders_to'][f['dst']]) < PEER_CAP:
            w['senders_to'][f['dst']].add(src_seat)

    # ── time passing ──────────────────────────────────────────────────────────
    def _roll(self, now):
        minute = int(now // MINUTE) * MINUTE
        if self._minute is not None and minute != self._minute:
            self._judge(self._minute, now)
            self._window = self._new_window()
        self._minute = minute
        for m in [m for m in self.minutes if m < now - HOUR - MINUTE]:
            del self.minutes[m]
        current_hour = int(now // HOUR) * HOUR
        for h in sorted(self.hours):
            if h < current_hour and not self.hours[h].get('closed'):
                self.hours[h]['closed'] = True
                self.closed_hours.append((h, self._public_hour(self.hours[h])))
        keep = settings()['retention_days'] * DAY
        for h in [h for h in self.hours if h < now - keep]:
            del self.hours[h]
        for key in [k for k, a in self.anomalies.items() if now - a['last_seen'] > ANOMALY_HOLD]:
            del self.anomalies[key]

    def tick(self, now=None):
        """Let time pass without new flows: closes minutes and hours, expires anomalies."""
        with self._lock:
            self._roll(time.time() if now is None else now)

    def take_closed_hours(self):
        with self._lock:
            out, self.closed_hours = self.closed_hours, []
            return out

    def _judge(self, minute, now):
        s, w = settings(), self._window
        found = []
        for seat, peers in w['peers'].items():
            if len(peers) >= s['p2p_peers'] or w['torrent'].get(seat, 0) >= 50_000_000:
                found.append(('p2p', seat, f'P2P or torrent traffic from seat {seat}',
                              f'{len(peers)} peers in one minute'))
        for seat, packets in w['packets_from'].items():
            if packets / MINUTE >= s['burst_pps']:
                found.append(('burst', seat, f'Packet burst from seat {seat}',
                              f'{round(packets / MINUTE):,} packets per second'))
        for dst, packets in w['packets_to'].items():
            senders = w['senders_to'].get(dst) or set()
            if packets / MINUTE >= s['burst_pps'] and len(senders) >= 3:
                where = self.seat_of.get(dst)
                found.append(('burst', where, f'DDoS-like burst towards {"seat " + where if where else dst}',
                              f'{round(packets / MINUTE):,} packets per second from {len(senders)} seats'))
        for seat in w['dhcp']:
            found.append(('rogue-dhcp', seat, f'Seat {seat} answers DHCP', 'a DHCP server that is not ours'))
        for seat in w['dns']:
            found.append(('rogue-dns', seat, f'Seat {seat} answers DNS to other seats', 'a DNS server at a seat'))
        for kind, seat, title, detail in found:
            key = f'{kind}:{seat}'
            old = self.anomalies.get(key)
            self.anomalies[key] = {'id': key, 'kind': kind, 'seat': seat, 'area': self.area_of.get(seat),
                                   'title': title, 'detail': detail, 'last_seen': minute + MINUTE,
                                   'first_seen': old['first_seen'] if old else minute}

    # ── reading ───────────────────────────────────────────────────────────────
    def _public_hour(self, h):
        """An hour as it may be kept past the retention: no seats, rare services folded."""
        min_seats = settings()['min_seats']
        services, other = {}, 0
        for name, svc in h['services'].items():
            if len(svc['seats']) >= min_seats:
                services[name] = {'bytes': svc['bytes'], 'category': svc['category'], 'seats': len(svc['seats'])}
            else:
                other += svc['bytes']
        return {'total': dict(h['total']), 'areas': {a: dict(c) for a, c in h['areas'].items()},
                'services': services, 'other_services': other}

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        s = settings()
        with self._lock:
            self._roll(now)
            hour_ago = [b for m, b in self.minutes.items() if m >= now - HOUR]
            series = [{'t': m, **dict(b['total'])} for m, b in sorted(self.minutes.items()) if m >= now - HOUR]
            day = [h for t, h in self.hours.items() if t > now - DAY - HOUR]
            mix_hour, areas = _cats(), defaultdict(_cats)
            for b in hour_ago:
                for c, v in b['total'].items():
                    mix_hour[c] += v
                for a, cats in b['areas'].items():
                    for c, v in cats.items():
                        areas[a][c] += v
            mix_day, services, seats = _cats(), {}, defaultdict(lambda: {'bytes': 0, 'mix': _cats()})
            for h in day:
                for c, v in h['total'].items():
                    mix_day[c] += v
                for name, svc in h['services'].items():
                    got = services.setdefault(name, {'bytes': 0, 'category': svc['category'], 'seats': set()})
                    got['bytes'] += svc['bytes']
                    got['seats'] |= svc['seats']
                for seat, v in h['seats'].items():
                    seats[seat]['bytes'] += v['bytes']
                    for c, b in v['mix'].items():
                        seats[seat]['mix'][c] += b
            named = [{'name': n, 'category': v['category'], 'bytes': v['bytes'], 'seats': len(v['seats'])}
                     for n, v in services.items() if len(v['seats']) >= s['min_seats']]
            folded = sum(v['bytes'] for v in services.values() if len(v['seats']) < s['min_seats'])
            out = {
                'updated': now, 'flows': self.flows,
                'exporters': [{'address': k, **v} for k, v in sorted(self.exporters.items())],
                'mix_hour': dict(mix_hour), 'mix_day': dict(mix_day), 'series': series,
                'areas': sorted(({'area': a, 'bytes': sum(c.values()), 'mix': dict(c)} for a, c in areas.items()),
                                key=lambda r: -r['bytes']),
                'services': sorted(named, key=lambda r: -r['bytes'])[:25], 'other_services': folded,
                'seats': sorted(({'seat': k, 'area': self.area_of.get(k), 'bytes': v['bytes'], 'mix': dict(v['mix'])}
                                 for k, v in seats.items()), key=lambda r: -r['bytes']),
                'anomalies': sorted(self.anomalies.values(), key=lambda a: -a['last_seen']),
                **s,
            }
        return out
