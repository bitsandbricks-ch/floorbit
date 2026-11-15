"""Pre-flight check board (issue #35). See docs/preflight.md.

Before doors open: is every placed switch reachable, is every uplink up, and do DHCP, DNS and the
other services on the health wall answer? Each group of checks runs on its own or all together.
The last result of each group is kept in data.json under ``preflight``, with when and by whom, so
the board and its printout show the state the crew signed off on.

The checks ask the sources directly. They never move the status monitor's or the health wall's
confirmed state, so running them doesn't send alerts.
"""
import threading
import time

from .store import load_data, save_data

KEY = 'preflight'
GROUPS = ('switches', 'uplinks', 'services')
PASS, WARN, FAIL, SKIP = 'pass', 'warn', 'fail', 'skip'
NOTHING_PLACED = 'No switch is placed on the floor plan.'

_lock = threading.Lock()


def _placed(data):
    from . import inventory
    return [d for d in inventory.devices(data) if d.get('role', 'switch') == 'switch' and d.get('name')
            and d.get('x') is not None]


def check_switches(data):
    from integrations.monitor import StatusMonitor

    from . import sources
    source = sources.monitoring()
    if not source.enabled():
        return [{'id': 'switches', 'name': 'Switches', 'status': SKIP,
                 'detail': 'No monitoring source is set up, so switch reachability can\'t be checked.'}]
    try:
        devices = source.devices() or []
    except Exception as exc:  # noqa: BLE001  # the board shows the failure instead of a 500
        return [{'id': 'switches', 'name': 'Switches', 'status': FAIL,
                 'detail': f'The monitoring source did not answer: {str(exc)[:200]}'}]
    out = []
    for sw in _placed(data):
        device = StatusMonitor.match(sw['name'], devices)
        status = StatusMonitor.device_status(device)
        out.append({'id': f"switch:{sw['id']}", 'name': sw['name'], 'switch_id': sw['id'],
                    'status': PASS if status == 'online' else FAIL,
                    'detail': {'online': 'Reachable', 'offline': 'Not reachable',
                               'unknown': 'Not found in the monitoring source (or ignored there)'}[status]})
    if not out:
        out.append({'id': 'switches', 'name': 'Switches', 'status': WARN, 'detail': NOTHING_PLACED})
    return out


def check_uplinks(data):
    from . import sources
    from .stats import _uplink_re
    source = sources.monitoring()
    if not source.enabled():
        return [{'id': 'uplinks', 'name': 'Uplinks', 'status': SKIP,
                 'detail': 'No monitoring source is set up, so uplinks can\'t be checked.'}]
    uplink = _uplink_re()
    out = []
    for sw in _placed(data):
        try:
            ports = source.device_ports(sw['name']) or []
        except Exception as exc:  # noqa: BLE001
            out.append({'id': f"uplinks:{sw['id']}", 'name': sw['name'], 'switch_id': sw['id'], 'status': FAIL,
                        'detail': f'Ports could not be read: {str(exc)[:200]}'})
            continue
        ups = [p for p in ports if uplink.search(str(p.get('description') or ''))]
        if not ups:
            out.append({'id': f"uplinks:{sw['id']}", 'name': sw['name'], 'switch_id': sw['id'], 'status': WARN,
                        'detail': 'No port is described as an uplink.'})
            continue
        for p in ups:
            up = str(p.get('state') or '').lower() == 'up'
            out.append({'id': f"uplink:{sw['id']}:{p.get('name')}", 'name': f"{sw['name']} {p.get('name')}",
                        'switch_id': sw['id'], 'status': PASS if up else FAIL,
                        'detail': (p.get('description') or '') + ('' if up else ' is down')})
    if not out:
        out.append({'id': 'uplinks', 'name': 'Uplinks', 'status': WARN, 'detail': NOTHING_PLACED})
    return out


def check_services(wall):
    if wall is None or not wall.registry.feeders('health'):
        return [{'id': 'services', 'name': 'DHCP, DNS and other services', 'status': WARN,
                 'detail': 'No health plugin is on. Turn on the DHCP and DNS checks under Settings > Plugins.'}]
    found, _ = wall._collect()   # ask now, without moving the wall's confirmed state
    status = {'up': PASS, 'warn': WARN, 'down': FAIL}
    return [{'id': f"service:{c['id']}", 'name': c['name'], 'kind': c.get('kind'),
             'status': status.get(c['status'], FAIL), 'detail': c.get('summary') or ''} for c in found]


def stored(data=None):
    data = data if data is not None else load_data()
    raw = data.get(KEY)
    return raw if isinstance(raw, dict) else {}


def board(data=None):
    saved = stored(data)
    groups = {g: saved.get(g) for g in GROUPS}
    items = [i for g in groups.values() if g for i in g['items']]
    counts = {s: sum(i['status'] == s for i in items) for s in (PASS, WARN, FAIL, SKIP)}
    ran = all(groups.values())
    return {'groups': groups, 'counts': counts, 'ready': ran and counts[FAIL] == 0,
            'complete': ran}


def run(groups, user, wall, now=None):
    now = time.time() if now is None else now
    data = load_data()
    results = {}
    for g in groups:
        if g == 'switches':
            items = check_switches(data)
        elif g == 'uplinks':
            items = check_uplinks(data)
        else:
            items = check_services(wall)
        results[g] = {'at': now, 'by': user, 'items': items}
    with _lock:
        data = load_data()
        data[KEY] = {**stored(data), **results}
        save_data(data)
    return board()


def pdf_report(result, event_name='', tz_offset_min=0):
    """One printable page (more when long): the verdict, then each group's checks."""
    from datetime import UTC, datetime, timedelta

    from . import pdf
    colours = {PASS: '#1f9d55', WARN: '#c27c0e', FAIL: '#d93025', SKIP: '#8a919c'}
    words = {PASS: 'OK', WARN: 'Check', FAIL: 'Failed', SKIP: 'Skipped'}
    tz = timedelta(minutes=-tz_offset_min)

    def stamp(ts):
        return (datetime.fromtimestamp(ts, tz=UTC) + tz).strftime('%Y-%m-%d %H:%M') if ts else '-'

    pages, page, y = [], pdf.Page(), 56.0

    def need(h):
        nonlocal page, y
        if y + h > pdf.A4[1] - 50:
            pages.append(page)
            page, y = pdf.Page(), 56.0

    page.text(48, y, f"Pre-flight check{': ' + event_name if event_name else ''}", size=20, bold=True)
    y += 26
    verdict = 'Ready for doors' if result['ready'] else (
        'Not ready' if result['complete'] else 'Not every check has run')
    page.text(48, y, verdict, size=13, bold=True, color=colours[PASS] if result['ready'] else colours[FAIL])
    c = result['counts']
    page.text(547, y, f"{c[PASS]} OK, {c[WARN]} to check, {c[FAIL]} failed, {c[SKIP]} skipped", size=9,
              color='#5b6370', align='right')
    y += 24
    titles = {'switches': 'Switches reachable', 'uplinks': 'Uplinks up', 'services': 'DHCP, DNS and services'}
    for g in GROUPS:
        group = result['groups'].get(g)
        need(40)
        page.text(48, y, titles[g], size=12, bold=True)
        page.text(547, y, f"{stamp(group['at'])}, {group['by'] or '-'}" if group else 'Not run', size=8,
                  color='#5b6370', align='right')
        y += 6
        page.line(48, y, 547, y)
        y += 14
        for item in (group or {}).get('items', []):
            need(16)
            page.rect(48, y - 8, 46, 11, fill=colours[item['status']])
            page.text(71, y, words[item['status']], size=7, bold=True, color='#ffffff', align='center')
            page.text(102, y, pdf.fit(item['name'], 9, 170), size=9, bold=True)
            page.text(280, y, pdf.fit(item.get('detail') or '', 8, 267), size=8, color='#5b6370')
            y += 15
        y += 10
    need(60)
    y += 20
    page.line(48, y, 250, y)
    page.line(320, y, 547, y)
    page.text(48, y + 12, 'Checked by', size=8, color='#5b6370')
    page.text(320, y + 12, 'Date and time', size=8, color='#5b6370')
    pages.append(page)
    return pdf.render(pages, title='Pre-flight check')
