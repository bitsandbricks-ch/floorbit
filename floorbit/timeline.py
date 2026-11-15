"""Event changelog (issue #100): one timeline of every change during the LAN. See docs/timeline.md.

Built from what Floorbit keeps anyway, plus a small journal for what it didn't:

- ``change`` and ``sign-in``: the audit log (who changed what, never the values).
- ``outage``: switches going offline and coming back (the stats store's event history).
- ``incident``: incidents opened and fixed (the incident board).
- ``alert``: security findings, power alerts, service health changes, the bandwidth forecast, log
  alerts and the monitoring source going away. These pass by on the event bus only, so they are
  written to ``timeline.jsonl`` as they happen, in the same words webhooks get: no MACs, IPs or nicks.
- ``deploy``: each start of Floorbit, with its version, and when the version changed.
"""
import datetime
import json
import os
import threading
import time

from . import store

KINDS = ('change', 'sign-in', 'outage', 'incident', 'alert', 'deploy')
MAX_BYTES = 2 * 1024 * 1024   # the journal; past this, the oldest half is dropped
MAX_ROWS = 2000               # one answer
ALERTS = ('security.finding', 'power.alert', 'health.changed', 'forecast.alert', 'logs.alert',
          'monitoring.offline', 'monitoring.online')
_lock = threading.Lock()


def path():
    return os.environ.get('TIMELINE_FILE') or os.path.join(
        os.path.dirname(os.path.abspath(store.DATA_FILE)), 'timeline.jsonl')


def write(kind, title, target='', t=None, **extra):
    entry = {'t': round(t if t is not None else time.time(), 3), 'kind': kind, 'title': str(title)[:200]}
    if target:
        entry['target'] = str(target)[:120]
    entry.update({k: v for k, v in extra.items() if v not in (None, '')})
    line = json.dumps(entry, separators=(',', ':'), default=str) + '\n'
    with _lock:
        try:
            with open(path(), 'a', encoding='utf-8') as f:
                f.write(line)
            _trim()
        except OSError as exc:   # a full disk must not break what was being logged
            print(f'[timeline] could not write the journal: {exc}')
    return entry


def _trim():
    p = path()
    if os.path.getsize(p) <= MAX_BYTES:
        return
    with open(p, encoding='utf-8') as f:
        lines = f.readlines()
    with open(p, 'w', encoding='utf-8') as f:
        f.writelines(lines[len(lines) // 2:])


def _journal():
    try:
        with open(path(), encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    out = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and isinstance(e.get('t'), (int, float)):
            out.append(e)
    return out


# ── Writing what passes by on the event bus ──────────────────────────────────────────────
def _pct(v):
    return f'{round(v)}%' if isinstance(v, (int, float)) else ''


def describe(event):
    """(title, target, severity) for an alert on the bus, or None. Words only, nothing personal."""
    from .webhooks import translate
    for name, d in translate(event):
        if name == 'security.finding':
            where = ' '.join(p for p in (d.get('switch'), d.get('port')) if p)
            seat = f" (seat {d['seat']})" if d.get('seat') else ''
            return f"Security: {str(d.get('kind') or 'finding').replace('_', ' ')}{seat}", where, d.get('severity')
        if name == 'power.alert':
            return (f"Power: {d.get('name')} at {_pct(d.get('pct'))} ({d.get('state')})", d.get('board') or '',
                    'down' if d.get('state') in ('tripped', 'overload') else 'warn')
        if name == 'health.changed':
            changes = d.get('changes') or []
            if not changes:
                return None
            text = ', '.join(f"{c.get('name')} {c.get('status')}" for c in changes[:5])
            bad = any(c.get('status') in ('down', 'critical') for c in changes)
            return f'Service health: {text}', '', 'down' if bad else 'info'
        if name == 'forecast.alert':
            return f"Bandwidth forecast: {_pct(d.get('pct'))} of the line expected", '', 'warn'
        if name == 'logs.alert':
            where = ' '.join(p for p in (d.get('device'), d.get('port')) if p)
            return f"Log alert: {d.get('title') or d.get('pattern')}", where, 'warn'
        if name == 'monitoring.offline':
            return 'Monitoring source unreachable', d.get('source') or '', 'down'
        if name == 'monitoring.online':
            return 'Monitoring source back', d.get('source') or '', 'up'
    return None


def on_event(event):
    if event.get('type') not in ALERTS:
        return
    found = describe(event)
    if found:
        title, target, severity = found
        write('alert', title, target, t=event.get('ts'), severity=severity, source=event.get('type'))


def record_start(version, data=None):
    """One ``deploy`` line per start; says so when the version changed since the last start."""
    starts = [e for e in _journal() if e.get('kind') == 'deploy']
    last = starts[-1].get('version') if starts else None
    if last and last != version:
        return write('deploy', f'Floorbit updated from {last} to {version}', version=version, severity='info')
    return write('deploy', f'Floorbit started (version {version})', version=version)


# ── Reading it all back ──────────────────────────────────────────────────────────────────
def _audit_rows():
    from . import audit
    rows, _total = audit.read(limit=10 ** 6)
    out = []
    for e in rows:
        try:
            t = datetime.datetime.strptime(e['time'], '%Y-%m-%dT%H:%M:%S%z').timestamp()
        except (KeyError, ValueError):
            continue
        kind = 'sign-in' if e.get('area') == 'sign-in' else 'change'
        title = e.get('action') or ''
        if e.get('fields'):
            title += f" ({', '.join(e['fields'][:6])})"
        out.append({'t': t, 'kind': kind, 'title': title, 'target': e.get('target') or '', 'who': e.get('user'),
                    'area': e.get('area'), 'severity': 'down' if e.get('ok') is False else None})
    return out


def _outages(switch_events):
    out, since = [], {}
    for t, sid, name, status in sorted(switch_events, key=lambda e: e[0]):
        key = sid or name
        if status == 'offline':
            since[key] = t
            out.append({'t': t, 'kind': 'outage', 'title': 'Switch went offline', 'target': name, 'severity': 'down'})
        elif status == 'online':
            took = t - since.pop(key) if key in since else None
            title = 'Switch back online' + (f' after {_took(took)}' if took is not None else '')
            out.append({'t': t, 'kind': 'outage', 'title': title, 'target': name, 'severity': 'up'})
    return out


def _took(seconds):
    m = round(seconds / 60)
    return f'{round(seconds)} s' if seconds < 90 else f'{m} min' if m < 120 else f'{m / 60:.1f} h'


def _incidents():
    from . import incidents
    out = []
    for i in incidents.list_all():
        where = (f"seat {i['seat']}" if i.get('seat') else i.get('switch_name') or i.get('circuit_name') or '')
        out.append({'t': i['created_at'], 'kind': 'incident', 'title': f"Incident opened: {i['title']}",
                    'target': where, 'severity': 'warn', 'id': i['id']})
        if i.get('fixed_at'):
            out.append({'t': i['fixed_at'], 'kind': 'incident', 'title': f"Incident fixed: {i['title']}",
                        'target': where, 'severity': 'up', 'id': i['id']})
    return out


def build(switch_events=(), kinds=None, q='', since=None, until=None, limit=MAX_ROWS):
    """Every entry, newest first, filtered. Returns (rows, total matching, counts per kind)."""
    rows = _audit_rows() + _outages(switch_events) + _incidents() + [
        {k: e.get(k) for k in ('t', 'kind', 'title', 'target', 'severity', 'version')} for e in _journal()]
    words = [w for w in str(q or '').lower().split() if w]
    counts = dict.fromkeys(KINDS, 0)
    picked = []
    for r in rows:
        if r.get('kind') not in counts:
            continue
        if (since is not None and r['t'] < since) or (until is not None and r['t'] >= until):
            continue
        text = ' '.join(str(r.get(k) or '') for k in ('title', 'target', 'who', 'area')).lower()
        if words and not all(w in text for w in words):
            continue
        counts[r['kind']] += 1
        if kinds and r['kind'] not in kinds:
            continue
        picked.append({k: v for k, v in r.items() if v not in (None, '')})
    # Newest first; two entries in the same millisecond keep the later-written one first.
    picked.reverse()
    picked.sort(key=lambda r: r['t'], reverse=True)
    return picked[:limit], len(picked), counts


def csv_text(rows):
    from .planner import _csv
    lines = ['time,kind,title,target,who']
    for r in rows:
        when = datetime.datetime.fromtimestamp(r['t']).astimezone().isoformat(timespec='seconds')
        lines.append(','.join(_csv(v) for v in (when, r['kind'], r.get('title', ''), r.get('target', ''),
                                                 r.get('who', ''))))
    return '\n'.join(lines) + '\n'


def init_timeline(app):
    from integrations import events
    events.subscribe_once('*', on_event)
    try:
        record_start(app.config.get('FLOORBIT_VERSION') or '0')
    except Exception as exc:  # noqa: BLE001 - the timeline must never stop the app from starting
        print(f'[timeline] could not note the start: {exc}')
