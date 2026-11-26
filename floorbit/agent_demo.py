"""Two made-up local agents for the demo (issue #998), so the Local agents pages can be seen and
screenshotted without a hall.

They are real rows in the agents list, marked ``demo``, so renaming them, their settings and the
plugins they leave off work as for any agent. Everything an agent would say about itself (that it
is connected, its report, its answers, its graphs, the devices it collects) is made up here while
the demo is on. They never take calls: ``agent_link`` leaves them out of routing and out of
``active()``, so the demo's monitoring keeps answering from the demo plugin, and with the demo off
they are hidden. Their keys match nothing, so nothing can sign in as one.
"""
import math
import time

AGENTS = (
    {'id': 'de30a001', 'name': 'Hall agent A', 'address': '192.0.2.21', 'primary': True},
    {'id': 'de30a002', 'name': 'Hall agent B', 'address': '192.0.2.22', 'primary': False},
)
GB = 1_000_000_000
VIP = '192.0.2.20'
VERSION = 'demo'
# The plugins whose data the demo agents report: the demo turns them on with the agents.
PLUGINS = ('syslog-relay', 'netflow-relay', 'telemetry')
STARTED = 6 * 3600          # "up for six hours"


def seed(data, now=None):
    """Add the demo agents to ``data`` when it has none at all. True when it changed."""
    if data.get('agents'):
        return False
    now = time.time() if now is None else now
    data['agents'] = [{'id': a['id'], 'name': a['name'], 'hash': '', 'created_at': now - 2 * 86400,
                       'created_by': 'demo', 'last_seen': None, 'version': None, 'address': None,
                       'demo': True} for a in AGENTS]
    return True


def is_demo(row):
    return bool(row and row.get('demo'))


def _spec(agent_id):
    return next((a for a in AGENTS if a['id'] == agent_id), None)


def _wave(seed, now, period=900.0):
    return 0.5 + 0.5 * math.sin(now / period * 2 * math.pi + seed)


def _telemetry(index, now, primary):
    devices = 14 if primary else 0
    heard = devices
    # Points since its start: one read of every device each half minute.
    points = int((STARTED + now % 600) / 30) * (1800 + 200 * index)
    return {'status': 'ok', 'message': 'Collecting' if primary else 'Standby: listens for traps only',
            'running': True, 'errors': [],
            'metrics': {'devices': devices, 'devices_heard': heard, 'devices_failing': 0,
                        'series': 2400 + 40 * index if primary else 0, 'points': points,
                        'polled_points': points // 3 if primary else 0, 'sent': points,
                        'telegraf_restarts': 0, 'split': 1, 'telegraf': 1, 'lookup': 1}}


def live(row, now, protocol):
    """``row`` (agent_link's public row) as a connected agent says it is."""
    spec = _spec(row['id']) or {'address': '192.0.2.29', 'primary': False}
    index = 0 if spec['primary'] else 1
    seen = now - 3 - index * 7
    received = int((now % 86400) * (2.5 - index))
    report = {
        'at': seen, 'up_seconds': STARTED + int(now % 600), 'reconnects': 0, 'link_drops': index,
        'calls_busy': 0, 'answers_failed': 0, 'syslog_received': received, 'syslog_sent': received,
        'syslog_dropped': 0, 'syslog_backlog': 0, 'flows_packets': int((now % 86400) * 12) if spec['primary'] else 0,
        'captive_shown': 18, 'captive_done': 160,
        'plugins': {'telemetry': _telemetry(index, now, spec['primary']),
                    'syslog-relay': {'status': 'ok', 'message': 'Relaying', 'running': True, 'errors': [],
                                     'metrics': {'received': received, 'dropped': 0}},
                    'netflow-relay': {'status': 'ok', 'message': 'Summing up flows', 'running': True,
                                      'errors': [], 'metrics': {}}},
        'vrrp': {'primary': spec['primary'], 'holds': [VIP] if spec['primary'] else []},
        # No "lease": the demo's pair is picked by VRRP, so its pages show that fallback too.
        'capabilities': ['split', 'syslog_hold', 'syslog_ids', 'plugin_updates', 'key_roll', 'cert'],
        'disk': {'auto': True, 'budget': 120 * GB, 'used': (64 if spec['primary'] else 3) * GB,
                 'kinds': {'flows': {'bytes': 61 * GB, 'files': 58, 'hours': 57.5, 'dropped': 0},
                           'buffer': {'bytes': 3 * GB, 'files': 412, 'hours': 0.4, 'dropped': 0}}
                 if spec['primary'] else {'buffer': {'bytes': 3 * GB, 'files': 405, 'hours': 0.4, 'dropped': 0}}},
        'settings': {'values': {}, 'key': 'stored',
                     'cert': {'not_after': now + 80 * 86400, 'names': [spec['address']], 'source': 'floorbit',
                              'floorbit_ca': True, 'public': False}},
    }
    calls = 420 - 160 * index
    return {**row, 'connected': True, 'last_seen': seen, 'version': VERSION, 'address': spec['address'],
            'protocol': protocol, 'transport': 'websocket', 'report': report,
            'stats': {'calls': calls, 'failed': 0, 'median_ms': 38 + 9 * index, 'last_error': None},
            'relays': {'syslog': {'at': seen, 'count': 300 - 120 * index}}
            if spec['primary'] else {'syslog': {'at': seen, 'count': 180}}}


def history(agent_id, hours, now=None, step=120):
    """{metric: [[time, value]]} like agent_history.history, made up for a demo agent."""
    now = time.time() if now is None else now
    primary = (_spec(agent_id) or {}).get('primary', False)
    start = now - hours * 3600
    times = [start + i * step for i in range(int(hours * 3600 // step) + 1)]
    series = {
        'points': lambda t: 3600 + 900 * _wave(0, t) if primary else 0.0,
        'sent': lambda t: 3600 + 900 * _wave(0, t) if primary else 0.0,
        'series': lambda t: 2400.0 if primary else 0.0,
        'heard': lambda t: 14.0 if primary else 0.0,
        'failing': lambda t: 0.0,
        'telegraf_restarts': lambda t: 0.0,
        'reconnects': lambda t: 0.0,
        'syslog': lambda t: (150 if primary else 90) + 60 * _wave(1, t, 1300),
        'median_ms': lambda t: (38 if primary else 47) + 12 * _wave(2, t, 700),
    }
    return {m: [[round(t), round(fn(t), 2)] for t in times] for m, fn in series.items()}


def devices_answer(given, agent_id, now=None):
    """What the telemetry plugin's ``devices`` call would answer: the primary collects every device
    it is given; the standby only listens."""
    now = time.time() if now is None else now
    primary = (_spec(agent_id) or {}).get('primary', False)
    rows = []
    for i, t in enumerate(given):
        rows.append({'name': t['name'], 'collects': primary, 'online': primary, 'seen': now - 5 - i % 25 if primary
                     else None, 'problems': [],
                     **({'ports': 52, 'macs': 20 + i % 30, 'neighbours': 2}
                        if primary and t.get('kind') == 'switch' else {})})
    return {'devices': rows, 'primary': primary}
