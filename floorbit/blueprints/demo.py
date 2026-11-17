"""Demo mode: the built-in ``demo`` plugin's made-up data, laid out on an empty floor plan.

The plugin (floorbit/builtin_plugins/demo) feeds the inventory, the seat mapping and the live
data. This module only places its switches and seat blocks, and only on a floor plan that is
still empty, so turning the demo on never moves anything someone placed by hand.

- ``POST /api/demo/layout`` (admins): sync the inventory and lay out the demo hall.
- With ``FLOORBIT_DEMO=1`` that happens once at start-up.
- Every page shows a "Demo data" banner while the plugin is on (``_theme_head.html``).
"""
import os
import uuid

from flask import Blueprint, current_app, jsonify

from .. import cable_plan, halls, inventory, plan_groups, plan_marks, port_areas
from ..store import load_data, save_data
from .inventory import data_lock, run_sync

bp = Blueprint('demo', __name__)


def _registry(app=None):
    return (app or current_app).extensions.get('floorbit_plugins')


def demo_on(app=None):
    registry = _registry(app)
    return bool(registry and registry.demo_on())


@bp.app_context_processor
def inject_demo():
    return {'demo_mode': demo_on()}


def _layout():
    spec = _registry().specs.get('demo')
    return getattr(spec.module, 'LAYOUT', None) if spec and spec.module else None


def seed():
    """Place the demo hall on an empty floor plan. Returns what it did."""
    layout = _layout()
    if not layout:
        return {'placed': 0, 'blocks': 0, 'skipped': 'the demo plugin has no layout'}
    run_sync()
    with data_lock:
        data = load_data()
        placed_already = any(d.get('x') is not None for d in inventory.devices(data))
        if placed_already or data.get('seat_blocks'):
            return {'placed': 0, 'blocks': 0, 'skipped': 'the floor plan is not empty'}
        # The first hall gets the plugin's hall name; the others are added after it.
        main = halls.ensure(data)[0]
        main['name'] = layout.get('hall') or main['name']
        spots = [(main['id'], layout['devices'], layout['blocks'], layout.get('marks') or [])]
        for spec in layout.get('halls') or []:
            hall = halls.create(data, spec['name'])
            spots.append((hall['id'], spec.get('devices') or {}, spec.get('blocks') or [], spec.get('marks') or []))
        placed, blocks = 0, []
        for hall_id, devices, hall_blocks, marks in spots:
            for dev in inventory.devices(data):
                pos = devices.get(dev['name'])
                if pos and 'demo' in (dev.get('refs') or {}):
                    inventory.update(data, dev['id'], {'x': pos[0], 'y': pos[1], 'hall_id': hall_id})
                    placed += 1
            blocks += [{'id': str(uuid.uuid4()), 'seat_width': 3, 'seat_height': 3, 'spacing_x': 0.5,
                        'spacing_y': 1, 'rotation': 0, 'reverse_numbers': False, 'hall_id': hall_id, **b}
                       for b in hall_blocks]
            data['seat_blocks'] = blocks
            for mark in marks:
                plan_marks.add(data, {**mark, 'hall_id': hall_id})
        _seed_power(data, layout)
        _seed_firewalls(data, layout)
        _seed_uplinks(data, layout)
        _seed_links(data, layout)
        _seed_panels(data, layout, main['id'])
        _seed_groups(data, layout, main['id'])
        _seed_areas(data, layout)
        if layout.get('cable_routes') and not data.get(cable_plan.KEY):
            data[cable_plan.KEY] = {cable_plan.lan_key(*k[4:].split('|', 1)): {**v, 'by': 'demo'}
                                    for k, v in layout['cable_routes'].items()}
        save_data(data)
    _import_cables()
    _seed_game_servers(layout)
    _seed_event()
    return {'placed': placed, 'blocks': len(blocks)}


def _import_cables():
    """The demo's patching, as an import from NetBox would bring it (block A through its panel)."""
    from .. import cables
    try:
        cables.import_from(_registry(), 'demo')
    except Exception as exc:  # noqa: BLE001  # the hall works without the cable list
        print(f'[demo] could not import the demo cables: {exc}')


def _seed_links(data, layout):
    """The uplinks with their cable type and planned speed, for the topology and the plan's cables."""
    if not layout.get('links') or data.get('links'):
        return
    data['links'] = [{'id': uuid.uuid4().hex[:12], 'note': '', 'by': 'demo', **link} for link in layout['links']]


def _seed_panels(data, layout, hall_id):
    if not layout.get('patch_panels') or data.get(cable_plan.PANELS_KEY):
        return
    data[cable_plan.PANELS_KEY] = [{**p, 'hall_id': hall_id} for p in layout['patch_panels']]


def _seed_groups(data, layout, hall_id):
    """Each block with its switches (and patch panel), so the editor moves them as one."""
    if data.get(plan_groups.KEY):
        return
    blocks = {b['name']: b['id'] for b in data.get('seat_blocks') or []}
    devices = {d['name']: d['id'] for d in inventory.devices(data)}
    for g in layout.get('groups') or []:
        members = ([{'kind': 'block', 'id': blocks[g['block']]}] if g['block'] in blocks else []) \
            + [{'kind': 'switch', 'id': devices[n]} for n in g['switches'] if n in devices] \
            + [{'kind': 'panel', 'id': p} for p in g['panels']]
        if len(members) > 1:
            plan_groups.add(data, {'name': g['name'], 'hall_id': hall_id, 'members': members})


def _seed_areas(data, layout):
    """Rough port areas where nobody wrote the patching down (the side hall)."""
    if data.get(port_areas.KEY):
        return
    areas = []
    for spec in layout.get('port_areas') or []:
        for a in port_areas.quick_entry(spec['switch'], spec['starts'], size=spec['size']):
            areas.append({'id': uuid.uuid4().hex[:12], **a, 'label': f"{a['seats'][0]}..{a['seats'][-1]}",
                          'updated_at': 0, 'by': 'demo'})
    if areas:
        data[port_areas.KEY] = areas


def _seed_power(data, layout):
    """The demo boards and circuits, on the blocks and switches just placed."""
    spec = layout.get('power')
    if not spec or (data.get('power') or {}).get('circuits'):
        return
    blocks = {b['name']: b['id'] for b in data.get('seat_blocks') or [] if b.get('name')}
    devices = {d['name']: d['id'] for d in inventory.devices(data)}
    boards = [{'id': uuid.uuid4().hex[:10], **b} for b in spec['boards']]
    board_ids = {b['name']: b['id'] for b in boards}
    circuits = []
    for c in spec['circuits']:
        circuits.append({'id': uuid.uuid4().hex[:10], 'board': board_ids[c['board']], 'name': c['name'],
                         'phase': c['phase'], 'rating_a': float(c['rating_a']), 'meter': c['meter'],
                         'blocks': [{'block': blocks[c['block']], 'rows': c.get('rows') or []}]
                         if c.get('block') in blocks else [],
                         'switches': [devices[n] for n in c.get('switches') or [] if n in devices],
                         'tripped': None, 'reading': None})
    data['power'] = {'boards': boards, 'circuits': circuits}


def _seed_firewalls(data, layout):
    """The demo's seat ranges, each on its firewall with the next one as backup."""
    spec = layout.get('firewalls')
    if not spec or (data.get('firewalls') or {}).get('ranges'):
        return
    data['firewalls'] = {'ranges': [{'id': uuid.uuid4().hex[:12], **r} for r in spec]}


def _seed_uplinks(data, layout):
    """The demo's internet lines and DNS resolvers, for the services page and the topology."""
    stored = data.get('services') if isinstance(data.get('services'), dict) else {}
    for kind in ('uplinks', 'resolvers'):
        if layout.get(kind) and not stored.get(kind):
            stored = {**stored, kind: [{'id': uuid.uuid4().hex[:12], **u} for u in layout[kind]]}
    data['services'] = stored


def _seed_game_servers(layout):
    """The demo's game servers, with an RCON password nobody needs to know (the demo answers anyway)."""
    import secrets

    from .. import game_servers
    if game_servers.listing():
        return
    for server in layout.get('game_servers') or []:
        body = {**server, 'rcon_password': secrets.token_urlsafe(18)} if server.get('rcon_port') else server
        try:
            game_servers.save(body)
        except Exception as exc:  # noqa: BLE001  # the hall works without its game servers
            print(f"[demo] could not add {server['name']}: {exc}")


# ── The event so far: crew, incidents, check-ins, status page, runbook, dashboards, schedule ──────
CREW = (('alex', 'Alex', 'tech', 'access'), ('sam', 'Sam', 'tech', 'operations'),
        ('robin', 'Robin', 'lead', 'electrics'))


def _seed_event(now=None):
    """What a day of the event leaves behind, so the crew pages aren't empty. Each part only when its
    page has nothing yet; a part that fails is skipped, never the demo."""
    import time
    now = time.time() if now is None else now
    from ..builtin_plugins.demo.texts import text
    words = text()
    for part in (_seed_crew, _seed_incidents, _seed_checkins, _seed_status, _seed_runbook, _seed_dashboards,
                 _seed_schedule, _seed_settings):
        try:
            part(words, now)
        except Exception as exc:  # noqa: BLE001  # a demo hiccup must not stop the rest
            print(f'[demo] {part.__name__[6:]}: {exc}')


def _seed_crew(_words, _now):
    """Three crew accounts without a password (nobody signs in as them), in the default teams."""
    from auth import teams
    users = current_app.extensions['auth'].users
    for username, name, role, team in CREW:
        if users.get(username) is None:
            users.add(username, display_name=name, role=role)
            teams.set_member(username, team, role)


def _seed_incidents(words, now):
    from .. import incidents
    with data_lock:
        data = load_data()
        if data.get(incidents.KEY):
            return
        circuits = {c.get('meter'): c for c in (data.get('power') or {}).get('circuits') or []}
        devices = {d['name']: d for d in inventory.devices(data)}
        items = []
        for where, problem, title, status, ago, assignee, team, notes in words['incidents']:
            kind, ref = where.split(':', 1)
            at = now - ago * 60
            if kind == 'seat':
                spot = {'seat': ref, 'switch_id': None}
            elif kind == 'switch' and ref in devices:
                spot = {'seat': None, 'switch_id': devices[ref]['id'], 'switch_name': ref}
            elif kind == 'circuit' and ref in circuits:
                spot = {'seat': None, 'switch_id': None, 'circuit_id': circuits[ref]['id'],
                        'circuit_name': circuits[ref]['name']}
            else:
                continue
            step = ago * 60 / (len(notes) + 1)
            items.append({
                'id': uuid.uuid4().hex[:12], **spot, 'title': title, 'problem': problem, 'team': team,
                'status': status, 'assignee': assignee, 'source': 'helpdesk' if problem else 'board',
                'reported_by': None if problem else 'demo', 'reports': 1, 'snapshot': None,
                'notes': [{'by': assignee or 'demo', 'at': at + step * (n + 1), 'text': t}
                          for n, t in enumerate(notes)],
                'created_at': at, 'updated_at': at + step * len(notes),
                **({'picked_up_at': at + 120} if assignee else {}),
                **({'fixed_at': at + step * len(notes)} if status == 'fixed' else {}),
            })
        data[incidents.KEY] = items
        save_data(data)


def _seed_checkins(_words, now):
    """Most players checked in with their seat card's PIN over the last day. In the side hall, where
    nobody wrote the patching down, the check-ins taught Floorbit most seats' ports; E-12's PIN card
    was swapped with E-4's, so it learned a port the port areas give to E-1..E-8 (a conflict to look at)."""
    from integrations import checkin, history

    from ..builtin_plugins.demo.plugin import SIDE_BLOCK, _ip, _mac, _seats, _switch_for, _taken
    from ..store import write_json
    if checkin.load_all():
        return
    rows, learned, events = {}, {}, []
    seats = [s for s in _seats() if _taken(s[3])]
    for n, (seat, block, number, i) in enumerate(seats):
        if n % 9 == 4:
            continue                    # online without a check-in: the crew sees these
        at = now - 22 * 3600 + (n * 997) % (20 * 3600)
        switch, port = _switch_for(block, number)
        if seat == f'{SIDE_BLOCK}-12':
            port = _switch_for(SIDE_BLOCK, 4)[1]
        rows[seat] = {'seat': seat, 'username': f'player-{i + 1:02d}', 'ip': _ip(i), 'mac': _mac(i),
                      'checked_in_at': at, 'last_seen': now - (n * 37) % 600, 'ip_changed': None,
                      'user_agent': None, 'pin_ok': True, 'device': 'pc', 'wired': 'verified',
                      'port_seen': {'switch': switch, 'port': port}, 'taken_from': None}
        if block == SIDE_BLOCK and number not in (7, 15):
            learned[seat] = {'switch': switch, 'port': port, 'learned_at': at, 'username': rows[seat]['username']}
        events.append((at, 'checkin', rows[seat], {}))
    # Two players moved seats during the night: the history keeps where they were first.
    for seat, old in (('C-20', 'C-6'), ('D-2', 'B-11')):
        if seat in rows:
            first = {**rows[seat], 'seat': old}
            events.append((rows[seat]['checked_in_at'] - 3 * 3600, 'checkin', first, {}))
            events.append((rows[seat]['checked_in_at'], 'moved', first, {'to_seat': seat}))
    checkin._save_all(rows)
    if learned:
        write_json(checkin._ports_path(), learned)
    for at, event, row, extra in sorted(events, key=lambda e: e[0]):
        history.record(event, row, ts=at, **extra)


def _seed_status(words, now):
    from .. import status_page
    if status_page._stored(load_data())['updates']:
        return
    for ago, state, area, message in reversed(words['status_updates']):
        update = status_page.post_update({'text': message, 'state': state, 'area': area}, 'demo')
        _backdate(status_page.KEY, 'updates', update['id'], now - ago * 60)
    start_in, minutes, area, message = words['maintenance']
    status_page.plan_maintenance({'start': now + start_in * 60, 'end': now + (start_in + minutes) * 60,
                                  'text': message, 'area': area}, 'demo', now=now)


def _backdate(key, part, item_id, at):
    with data_lock:
        data = load_data()
        for item in (data.get(key) or {}).get(part) or []:
            if item.get('id') == item_id:
                item['at'] = at
        save_data(data)


def _seed_runbook(words, _now):
    """The starters plus one of the event's own, as a crew would write it."""
    from .. import runbooks
    if isinstance(load_data().get(runbooks.KEY), list):
        return
    title, kinds, body = words['runbook']
    runbooks.add({'title': title, 'kinds': kinds, 'body': body}, 'demo')


def _seed_dashboards(words, _now):
    from .. import dashboard_layouts
    if dashboard_layouts.all_layouts():
        return
    tiles = {'noc-wall': ['problems', 'incidents', 'switches', 'seats'], 'ops-desk': ['incidents', 'problems']}
    for layout_id, name, columns in words['layouts']:
        dashboard_layouts.save(layout_id, {'name': name, 'columns': columns,
                                           'tiles': [f'floorbit/w/{t}' for t in tiles[layout_id]]}, 'demo')


def _seed_schedule(words, now):
    from .. import schedule
    if schedule.get()['items']:
        return
    import time
    hour = 3600
    # Real clock times read better than "an hour ago": the event runs from yesterday afternoon to tonight.
    day = time.localtime(now)
    base = time.mktime((day.tm_year, day.tm_mon, day.tm_mday, 0, 0, 0, 0, 0, -1))
    schedule.set_event({'start': base - 8 * hour, 'end': base + 20 * hour})
    for start, length, kind, title, where in words['schedule']:
        schedule.add({'title': title, 'kind': kind, 'where': where, 'start': base + start * hour,
                      'end': base + (start + length) * hour if length else None}, 'demo')


def _seed_settings(_words, _now):
    """Check-in, the public status page and the schedule on, so their pages show up."""
    store = current_app.extensions.get('floorbit_settings')
    if store is None:
        return
    for key in ('integrations.checkin_enabled', 'public.status_page', 'public.schedule'):
        try:
            if store.source(key) != 'saved':
                store.update({key: True})
        except Exception as exc:  # noqa: BLE001  # a setting this install doesn't have
            print(f'[demo] could not turn on {key}: {exc}')


@bp.route('/api/demo/layout', methods=['POST'])
def lay_out():
    if not demo_on():
        return jsonify({'error': 'Turn on the demo data plugin first (Settings > Plugins).'}), 409
    install_stand_in(current_app)
    return jsonify(seed())


def install_stand_in(app):
    """While the demo is on, its made-up DNS servers, internet lines and game servers answer the probes,
    game queries and RCON commands themselves (the plugin's ``answer``), so nothing is sent out."""
    from .. import probes
    from ..plugins import Context
    registry = _registry(app)
    if registry is None:
        return

    def answer(method, args):
        spec = registry.specs.get('demo')
        if spec is None or not registry.demo_on() or spec.plugin_class() is None:
            return None
        return spec.plugin_class()(Context(spec, registry)).answer(method, args)

    probes.stand_in(answer)


def seed_on_start(app):
    """FLOORBIT_DEMO=1: one switch for a filled-in demo. Never fatal."""
    install_stand_in(app)
    if os.environ.get('FLOORBIT_DEMO', '').strip().lower() not in ('1', 'true', 'yes', 'on'):
        return
    with app.app_context():
        try:
            result = seed()
            print(f"[demo] {result}")
        except Exception as exc:  # noqa: BLE001  # a demo hiccup must not stop the app
            print(f"[demo] could not lay out the demo hall: {exc}")
        stats = app.extensions.get('floorbit_stats')
        if stats is not None:
            history = demo_history()
            stats.backfill(history)
            stats.backfill_seats(*demo_seat_history(history))
            stats.backfill_event(*demo_event_history(history))
        from .flows import init_demo_flows
        init_demo_flows(app)
        lancache = app.extensions.get('floorbit_lancache')
        if lancache is not None:
            lancache.start_demo()
        receiver = app.extensions.get('floorbit_syslog')
        if receiver is not None:
            from ..syslog import start_demo
            start_demo(receiver)


def demo_history(now=None, step=120):
    """A made-up last day for the stats dashboard: doors open, the hall fills up over the first
    hours, then quiet at night and busy in the evening."""
    import math
    import time

    from ..builtin_plugins.demo.plugin import PORTS, _model, _switches, _uplinks
    now = time.time() if now is None else now
    # Every port of every switch is read, so most of them are down: nothing is plugged in.
    ports = sum(len(PORTS[_model(name)]) for name, _role, _i in _switches())
    links = 2 * len(_uplinks())
    out = []
    start = now - 24 * 3600
    for k in range(24 * 3600 // step, 0, -1):
        t = now - k * step
        hour = time.localtime(t).tm_hour + time.localtime(t).tm_min / 60
        busy = 0.15 + 0.85 * max(0.0, math.sin((hour - 9) / 24 * 2 * math.pi)) ** 2
        jitter = 0.9 + 0.2 * math.sin(t / 700) * math.cos(t / 1900)
        arrived = min(1.0, (t - start) / (4 * 3600))
        online = round((70 + 15 * busy) * arrived)
        down = 3.3e9 * (0.55 + 0.45 * busy) * jitter * max(0.05, arrived)   # about what the live demo hall sends
        out.append({'t': t, 'down': round(down), 'up': round(down * 0.14), 'online': online,
                    'ports_up': online + links, 'ports_down': ports - online - links, 'ports_errors': 0})
    return out


def demo_seat_history(samples):
    """Seat changes that match ``demo_history``'s online counts: seats come in a made-up order and
    leave in reverse, so the replay shows the hall filling up. Returns (events, start)."""
    import random

    from ..builtin_plugins.demo.plugin import _seats
    order = [seat for seat, _b, _n, _i in _seats()]
    random.Random(18).shuffle(order)
    events, online = [], 0
    for sample in samples:
        n = min(sample['online'], len(order))
        events += [[sample['t'], seat, 1] for seat in order[online:n]]
        events += [[sample['t'], seat, 0] for seat in order[n:online]]
        online = n
    return events, samples[0]['t'] if samples else None


def demo_event_history(samples):
    """Made-up outages and problem ports for the demo's report: one access switch lost power for a
    while, one distribution switch rebooted, and a few seat ports flapped or ran at half duplex."""
    if not samples:
        return [], {}
    start, end = samples[0]['t'], samples[-1]['t']
    span = end - start
    outages = [
        [start + span * at + took * k, name, name, ('offline', 'online')[k]]
        for name, at, took in (('sw-c-02', 0.31, 1260), ('dist-02', 0.55, 240), ('sw-c-02', 0.72, 420))
        for k in (0, 1)
    ]
    from ..builtin_plugins.demo.plugin import _switch_for
    ports = {}
    for i, (seat, kinds) in enumerate([('B-7', {'flapping': 9, 'errors': 3}), ('D-14', {'flapping': 6}),
                                       ('A-3', {'duplex': 4}), ('C-22', {'errors': 3}), ('A-18', {'flapping': 2})]):
        block, number = seat.split('-')
        switch, port = _switch_for(block, int(number))
        ports[f'{switch}|{port}'] = {'switch': switch, 'port': port, 'seat': seat, 'count': sum(kinds.values()),
                                     'kinds': kinds, 'last': end - i * 1800}
    return outages, ports
