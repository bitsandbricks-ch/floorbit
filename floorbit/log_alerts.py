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

    def observe(self, line, now=None):
        """Count one kept line. Returns the item when the line started a new one."""
        pid = match(line.get('message'))
        if not pid:
            return None
        now = time.time() if now is None else now
        device = str(line.get('device') or '')
        key = f"log:{pid}:{device.lower()}:{line.get('port') or ''}"
        with self._lock:
            self._prune(now)
            item = self.items.get(key)
            if item:
                item['count'] += 1
                item['last'] = now
                item['seat'] = item['seat'] or line.get('seat')
                return None
            item = self.items[key] = {
                'id': key, 'kind': 'log', 'pattern': pid, 'title': TITLES[pid], 'device': device,
                'port': line.get('port'), 'seat': line.get('seat'), 'since': now, 'last': now, 'count': 1,
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


def markers(lines, devices, now=None, minutes=10):
    """Warnings and worse of the last minutes per seat and per switch, for the floor plan.

    ``devices`` maps a switch name (lower case) to its id. Counts only: what the lines say stays
    on the Logs page."""
    from .syslog import SEVERITIES
    now = time.time() if now is None else now
    worst = SEVERITIES.index('warning')
    seats, switches = {}, {}
    for line in reversed(lines):
        if line['ts'] < now - minutes * 60:
            if line['ts'] < now - minutes * 60 - 300:   # lines arrive in order, give or take a clock
                break
            continue
        if SEVERITIES.index(line['severity']) > worst:
            continue
        if line.get('seat'):
            seats[line['seat']] = seats.get(line['seat'], 0) + 1
        else:
            sid = devices.get(str(line.get('device') or '').lower())
            if sid:
                switches[sid] = switches.get(sid, 0) + 1
    return {'seats': seats, 'switches': switches, 'minutes': minutes}
