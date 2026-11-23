"""The choices for every field that names something Floorbit already knows: switches, their ports,
seats, blocks, rows, halls, firewalls, agents, users, teams, patch panels and their ports.

A switch or a seat is never typed in: the page asks ``GET /api/options/<kind>`` and shows a
searchable list (``frontend/src/components/ui/EntitySelect.tsx``). One endpoint, one component, so
every form gets the same choices the same way.

Each option is ``{"value", "label", "group"?, "hint"?, "used"?}``. ``used`` says what already holds
it (a port with a cable): ports list free ones first and say who holds the rest.
"""
import re

from flask import Blueprint, current_app, jsonify, request

from .. import cables, halls, incidents, inventory
from ..store import load_data

bp = Blueprint('options', __name__)

INFRA_ROLES = {'firewall', 'server', 'router', 'core'}


def _natural(text):
    """'Gi1/0/10' after 'Gi1/0/9', 'A-10' after 'A-9'."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', str(text or ''))]


def _can(permission):
    from auth import current_user, roles  # late: auth imports floorbit while it loads
    auth = current_app.extensions.get('auth')
    if not auth or not auth.enabled:
        return True
    user = current_user()
    return bool(user and roles.can(user, permission))


def _switches(data):
    out = []
    for dev in inventory.devices(data):
        if not dev.get('name'):
            continue
        role = str(dev.get('role') or '').lower()
        out.append({'value': dev['name'], 'label': dev['name'],
                    'group': 'infrastructure' if role in INFRA_ROLES else 'switches'})
    return sorted(out, key=lambda o: (o['group'] != 'switches', _natural(o['label'])))


def _ports(data, switch):
    """The switch's ports from the monitoring source, with what holds each one."""
    from .. import sources
    from ..syslog import canonical_port
    if not switch:
        return []
    names, seen = [], set()
    for p in sources.monitoring().device_ports(switch) or []:
        # One entry per port even when a source lists it twice: a picker can't hold the same
        # value twice (Mantine refuses it and the whole form breaks, #972).
        if p.get('name') and p['name'] not in seen:
            seen.add(p['name'])
            names.append(p['name'])
    held = {}
    for c in cables.all_cables(data):
        if c['switch'].lower() == switch.lower():
            held[canonical_port(c['port'])] = c.get('seat') or c.get('label')
    from integrations import seat_sources
    for seat, m in (seat_sources.load() or {}).items():   # hand entries and ports check-ins found
        if str(m.get('switch') or '').lower() == switch.lower() and m.get('port'):
            held.setdefault(canonical_port(m['port']), seat)
    for c in cables.all_cables(data):   # a cabled port the source doesn't list (switch away) still shows
        if c['switch'].lower() == switch.lower() and c['port'] not in seen:
            seen.add(c['port'])
            names.append(c['port'])
    out = [{'value': n, 'label': n, 'used': held.get(canonical_port(n))} for n in names]
    return sorted(out, key=lambda o: (bool(o['used']), _natural(o['value'])))


def _panels(data):
    """Patch panels: the ones placed on a plan (with their port count) and names cables give."""
    from .. import cable_plan
    size = lambda p: str(p.get('ports') or cable_plan.PANEL_PORTS)   # noqa: E731
    out = {p['name'].lower(): {'value': p['name'], 'label': p['name'], 'hint': size(p)}
           for p in cable_plan.panels(data)}
    for c in cables.all_cables(data):
        if c.get('panel') and c['panel'].lower() not in out:
            out[c['panel'].lower()] = {'value': c['panel'], 'label': c['panel']}
    return sorted(out.values(), key=lambda o: _natural(o['value']))


def _seats(data):
    out = [{'value': s, 'label': s, 'group': s.rsplit('-', 1)[0] if '-' in s else ''}
           for s in incidents.seat_numbers(data)]
    return sorted(out, key=lambda o: _natural(o['value']))


def _blocks(data):
    """Every seat block by its id, under what people call it: a block named by its rows has no
    name of its own, so it goes by its row letters ("C to D")."""
    from ..seat_names import label
    from ..seat_rows import seat_count
    out = [{'value': b['id'], 'label': label(b) or b['id'], 'hint': str(seat_count(b))}
           for b in data.get('seat_blocks') or [] if b.get('id')]
    return sorted(out, key=lambda o: _natural(o['label']))


def _halls(data):
    return [{'value': h['id'], 'label': h.get('name') or h['id']} for h in halls.halls(data)]


def _firewalls(data):
    return sorted(({'value': d['name'], 'label': d['name']} for d in inventory.devices(data)
                   if d.get('role') == 'firewall' and d.get('name')), key=lambda o: _natural(o['value']))


def _agents(_data):
    from .. import agent_link
    # By id: a renamed agent keeps the devices given to it (telemetry_agent).
    return [{'value': a['id'], 'label': a.get('name') or a['id'], 'hint': a['id']}
            for a in agent_link.all_agents(_data)]


def _users(_data):
    auth = current_app.extensions.get('auth')
    users = auth.users.list() if auth else []
    return sorted(({'value': u['username'], 'label': u.get('display_name') or u['username'],
                    'hint': u['username']} for u in users), key=lambda o: o['label'].lower())


def _teams(_data):
    from auth import teams
    return [{'value': t['id'], 'label': t['name']} for t in teams.all_teams().values()]


def _devices(data):
    """Every inventory device, grouped by role (a VM's host, ...). Links go by name, so two devices
    with the same name (a plugin's and one added by hand) are one option."""
    seen, out = set(), []
    for d in inventory.devices(data):
        name = d.get('name')
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append({'value': name, 'label': name, 'group': d.get('role') or 'other'})
    return sorted(out, key=lambda o: (o['group'], _natural(o['label'])))


def _dashboards(data):
    from .. import dashboards
    return sorted(({'value': b['id'], 'label': b.get('name') or b['id']} for b in dashboards.all_layouts(data)),
                  key=lambda o: _natural(o['label']))


def _pages(_data):
    """The pages this account may open, for links to them (the sidebar's own sections)."""
    from .. import page_index
    ctx = {}
    current_app.update_template_context(ctx)
    return [{'value': p['id'], 'label': p['label'], 'hint': p['href']} for p in page_index.for_context(ctx)]


def _rows(data):
    """Rows by name, grouped by their block (C and D under the block C to D); the hint is the seat
    count. A row of a block numbered as a whole is the block and the row: "A 2"."""
    from ..seat_names import hall_rows, row_label
    return [{'value': r['id'], 'label': row_label(r), 'group': r['block_label'], 'hint': str(len(r['seats']))}
            for r in hall_rows(data)]


KINDS = {
    'devices': ('floorplan.view', _devices),
    'switches': ('floorplan.view', _switches),
    'seats': ('floorplan.view', _seats),
    'panels': ('floorplan.view', _panels),
    'blocks': ('floorplan.view', _blocks),
    'rows': ('floorplan.view', _rows),
    'halls': ('floorplan.view', _halls),
    'firewalls': ('floorplan.view', _firewalls),
    'agents': ('settings.manage', _agents),
    'dashboards': ('floorplan.view', _dashboards),
    'pages': ('floorplan.view', _pages),
    'users': ('incidents.assign', _users),
    'teams': ('incidents.assign', _teams),
}


@bp.route('/api/options/<kind>', methods=['GET'])
def options(kind):
    data = load_data()
    if kind == 'ports':
        if not _can('floorplan.view'):
            return jsonify({'error': 'Not allowed.'}), 403
        return jsonify({'options': _ports(data, (request.args.get('switch') or '').strip())})
    if kind == 'panel-ports':
        from .. import cable_plan
        if not _can('floorplan.view'):
            return jsonify({'error': 'Not allowed.'}), 403
        return jsonify({'options': cable_plan.panel_ports(data, (request.args.get('panel') or '').strip())})
    if kind not in KINDS:
        return jsonify({'error': 'Unknown list.'}), 404
    permission, make = KINDS[kind]
    if not _can(permission):
        return jsonify({'error': 'Not allowed.'}), 403
    return jsonify({'options': make(data)})
