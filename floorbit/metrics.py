"""Prometheus metrics (issue #153): Floorbit's own counts in the text exposition format, for a NOC's
Grafana. Aggregate only, per hall at most: no seats, nicks or addresses, so the five-seat privacy
rule never comes into it. See docs/metrics.md.
"""
import time

from flask import current_app

from . import halls, incidents, seat_view
from .store import load_data

STATES = ('online', 'offline', 'unknown')


def _escape(value):
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


class _Out:
    def __init__(self):
        self.lines = []

    def metric(self, name, kind, help_text, samples):
        self.lines += [f'# HELP {name} {help_text}', f'# TYPE {name} {kind}']
        for labels, value in samples:
            tag = ','.join(f'{k}="{_escape(v)}"' for k, v in labels.items())
            self.lines.append(f'{name}{{{tag}}} {value}' if tag else f'{name} {value}')

    def text(self):
        return '\n'.join(self.lines) + '\n'


def render(now=None):
    now = time.time() if now is None else now
    data = load_data()
    out = _Out()
    seats, checked, problems, last_read = [], [], [], None
    for hall in halls.halls(data):
        v = seat_view.view(hall['id'], now=now)
        name = hall['name']
        counts = dict.fromkeys(STATES, 0)
        for s in v['seats'].values():
            counts[s['state']] += 1
        seats += [({'hall': name, 'state': st}, n) for st, n in counts.items()]
        if v['checkin']:
            checked.append(({'hall': name}, sum(1 for s in v['seats'].values() if s.get('checked_in'))))
        problems.append(({'hall': name}, sum(1 for s in v['seats'].values() if s.get('problems'))))
        last_read = v['last_read'] or last_read
    out.metric('floorbit_seats', 'gauge', 'Seats by state: online (port up), offline (port down), unknown.', seats)
    out.metric('floorbit_seats_with_problems', 'gauge', 'Seats with an open incident or port trouble.', problems)
    if checked:
        out.metric('floorbit_seats_checked_in', 'gauge', 'Seats with a check-in.', checked)

    by_status = dict.fromkeys(incidents.STATUSES, 0)
    for i in incidents.list_all():
        by_status[i.get('status')] = by_status.get(i.get('status'), 0) + 1
    out.metric('floorbit_incidents', 'gauge', 'Incidents by status.',
               [({'status': k}, n) for k, n in by_status.items()])

    monitor = (current_app.extensions.get('lal_integrations') or {}).get('monitor')
    switches = {}
    for st in (getattr(monitor, 'statuses', None) or {}).values():
        key = st.get('status') or 'unknown'
        switches[key] = switches.get(key, 0) + 1
    out.metric('floorbit_switches', 'gauge', 'Monitored switches by status.',
               [({'status': k}, n) for k, n in sorted(switches.items())])

    watch = current_app.extensions.get('floorbit_attention')
    kinds = {}
    for item in (watch.snapshot()['items'] if watch else []):
        kinds[item.get('kind') or 'other'] = kinds.get(item.get('kind') or 'other', 0) + 1
    out.metric('floorbit_attention_items', 'gauge', 'Needs-attention items by kind.',
               [({'kind': k}, n) for k, n in sorted(kinds.items())])

    if last_read:
        out.metric('floorbit_port_read_age_seconds', 'gauge', 'Seconds since the last switch port read.',
                   [({}, round(now - last_read, 1))])
    version = current_app.config.get('FLOORBIT_VERSION') or '0'
    out.metric('floorbit_info', 'gauge', 'Floorbit version.', [({'version': version}, 1)])
    return out.text()
