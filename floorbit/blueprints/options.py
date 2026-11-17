"""The choices for every field that names something Floorbit already knows: switches, their ports,
seats, blocks, halls, firewalls, agents, users, teams, patch panels and their ports.

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
    names = [p.get('name') for p in sources.monitoring().device_ports(switch) or [] if p.get('name')]
    held = {}
    for c in cables.all_cables(data):
        if c['switch'].lower() == switch.lower():
            held[canonical_port(c['port'])] = c.get('seat') or c.get('label')
    from integrations import seat_sources
    for seat, m in (seat_sources.load() or {}).items():   # hand entries and ports check-ins found
        if str(m.get('switch') or '').lower() == switch.lower() and m.get('port'):
            held.setdefault(canonical_port(m['port']), seat)
    for c in cables.all_cables(data):   # a cabled port the source doesn't list (switch away) still shows
        if c['switch'].lower() == switch.lower() and c['port'] not in names:
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
    size = lambda b: int(b.get('cols') or 0) * int(b.get('rows') or 0)   # noqa: E731
    return sorted(({'value': b['name'], 'label': b['name'], 'hint': str(size(b))}
                   for b in data.get('seat_blocks') or [] if b.get('name')), key=lambda o: _natural(o['value']))


def _halls(data):
    return [{'value': h['id'], 'label': h.get('name') or h['id']} for h in halls.halls(data)]


def _firewalls(data):
    return sorted(({'value': d['name'], 'label': d['name']} for d in inventory.devices(data)
                   if d.get('role') == 'firewall' and d.get('name')), key=lambda o: _natural(o['value']))


def _agents(_data):
    from .. import agent_link
    return [{'value': a['name'], 'label': a['name']} for a in agent_link.all_agents(_data) if a.get('name')]


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


KINDS = {
    'devices': ('floorplan.view', _devices),
    'switches': ('floorplan.view', _switches),
    'seats': ('floorplan.view', _seats),
    'panels': ('floorplan.view', _panels),
    'blocks': ('floorplan.view', _blocks),
    'halls': ('floorplan.view', _halls),
    'firewalls': ('floorplan.view', _firewalls),
    'agents': ('settings.manage', _agents),
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
