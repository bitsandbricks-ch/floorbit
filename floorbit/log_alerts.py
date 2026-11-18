"""Log alerts (issue #92): syslog lines that match a known pattern become needs-attention items on
the Problems page, and lines about a port light up its seat on the floor plan. See docs/syslog.md.

A flood is one item: lines with the same pattern from the same device and port add to one item's
count until it has been quiet for ``LOG_ALERT_MINUTES`` (15). Items hold the pattern's title, the
switch, the port and the seat, never the line itself (lines can name MACs and IPs).
"""
import re
import threading
import time

from integrations import config, events

# (id, pattern, title). Cisco IOS names first, then the words other vendors use.
PATTERNS = (
    ('err_disable', re.compile(r'ERR_DISABLE|err-?disable', re.I), 'Port shut down by the switch (err-disable)'),
    ('port_security', re.compile(r'PSECURE_VIOLATION|PORT_SECURITY|port.security violation', re.I),
     'Port security violation'),
    ('dhcp_snooping', re.compile(r'DHCP_SNOOPING|dhcp.snooping', re.I), 'DHCP snooping dropped packets'),
    ('mac_flap', re.compile(r'MACFLAP|MAC_MOVE|flapping between port', re.I), 'MAC address moving between ports'),
    ('loop', re.compile(r'LOOP_?(?:BACK_)?DETECT|loop(?:-?back)? detected', re.I), 'Loop detected'),
    ('storm', re.compile(r'STORM_CONTROL|storm.control', re.I), 'Storm control'),
    ('stp', re.compile(r'SPANTREE|TOPOLOGY_?CHANGE|topology change|\bTCN\b', re.I), 'Spanning tree topology change'),
)
TITLES = {pid: title for pid, _rx, title in PATTERNS}
# A storm on every port of a big hall (a loop, a TCN flood) must not grow the list without end:
# past this many items new ones fold into one per switch, past twice it into one per pattern.
MAX_ITEMS = 5000


def quiet_seconds():
    return config.get_int('LOG_ALERT_MINUTES', 15, minimum=1) * 60


def match(message):
    """The first pattern a line matches, or None."""
    for pid, rx, _title in PATTERNS:
        if rx.search(message or ''):
            return pid
    return None


class LogAlerts:
    def __init__(self):
        self._lock = threading.Lock()
        self.items = {}   # id -> item
        self._pruned = 0.0

    def observe(self, line, now=None):
        """Count one kept line. Returns the item when the line started a new one."""
        pid = match(line.get('message'))
        if not pid:
            return None
        now = time.time() if now is None else now
        device = str(line.get('device') or '')
        port, seat = line.get('port') or '', line.get('seat')
        key = f"log:{pid}:{device.lower()}:{port}"
        with self._lock:
            # Once a second, not per line: with every port of 400 switches flapping the list is
            # tens of thousands long, and a scan per line held a 500-lines-a-second hall back.
            if now - self._pruned >= 1 or now < self._pruned:
                self._prune(now)
                self._pruned = now
            if key not in self.items and len(self.items) >= MAX_ITEMS:
                port, seat = '', None
                key = f"log:{pid}:{device.lower()}:"
                if key not in self.items and len(self.items) >= 2 * MAX_ITEMS:
                    device = ''
                    key = f"log:{pid}::"
            item = self.items.get(key)
            if item:
                item['count'] += 1
                item['last'] = now
                item['seat'] = item['seat'] or seat
                return None
            item = self.items[key] = {
                'id': key, 'kind': 'log', 'pattern': pid, 'title': TITLES[pid], 'device': device,
                'port': port or None, 'seat': seat, 'since': now, 'last': now, 'count': 1,
                'line_id': line.get('id'),
            }
        events.publish('logs.alert', {k: item[k] for k in ('id', 'pattern', 'title', 'device', 'port', 'seat')})
        events.publish('attention.changed', {})
        return item

    def _prune(self, now):
        quiet = quiet_seconds()
        for key in [k for k, v in self.items.items() if now - v['last'] > quiet]:
            del self.items[key]

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            self._prune(now)
            return sorted((dict(v) for v in self.items.values()), key=lambda i: -i['since'])


OLD_RUN = 200


def markers(lines, devices, now=None, minutes=10):
    """Warnings and worse of the last minutes per seat and per switch, for the floor plan.

    ``devices`` maps a switch name (lower case) to its id. Counts only: what the lines say stays
    on the Logs page."""
    from .syslog import SEVERITIES
    now = time.time() if now is None else now
    worst = SEVERITIES.index('warning')
    seats, switches = {}, {}
    old = 0
    for line in reversed(lines):
        if line['ts'] < now - minutes * 60:
            # Lines mostly arrive in order, so a run of old ones means the rest are older still. A run,
            # not one: a sender's own clock, or a local agent's buffered lines, can put an old one late.
            old += 1
            if old >= OLD_RUN:
                break
            continue
        old = 0
        if SEVERITIES.index(line['severity']) > worst:
            continue
        if line.get('seat'):
            seats[line['seat']] = seats.get(line['seat'], 0) + 1
        else:
            sid = devices.get(str(line.get('device') or '').lower())
            if sid:
                switches[sid] = switches.get(sid, 0) + 1
    return {'seats': seats, 'switches': switches, 'minutes': minutes}
