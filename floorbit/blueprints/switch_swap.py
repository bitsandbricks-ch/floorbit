"""Swap a dead switch for a spare (issue #1060). The rules live in floorbit/switch_swap.py.

- ``GET /switch-swap/<id>``: the page (React).
- ``GET /api/switch-swap/<id>``: the switch, whether it is down, the spares on the shelf, its last
  config copy (with ``configs.read``), the seat ports to patch back and its open incident.
- ``POST /api/switch-swap/<id>``: ``{spare_id}`` or ``{serial, model}``: the new box is in.

Reading needs ``floorplan.view``, swapping ``floorplan.edit`` like any inventory change (auth/roles.py).
"""
import contextlib

from flask import Blueprint, current_app, g, jsonify, request

from .. import audit, spa, switch_swap
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('switch_swap', __name__)


def _user():
    from auth import current_user  # late: auth imports floorbit while it loads
    return current_user()


def _can(permission):
    from auth import roles
    if not current_app.extensions['auth'].enabled:
        return True
    user = _user()
    return bool(user and roles.can(user, permission))


def _status(device_id):
    monitor = (current_app.extensions.get('floorbit_integrations') or {}).get('monitor')
    return dict((getattr(monitor, 'statuses', None) or {}).get(device_id) or {})


def _plan(device_id):
    from integrations import seat_sources
    return switch_swap.plan(load_data(), device_id, _status(device_id), _can('configs.read'), seat_sources.load())


@bp.route('/switch-swap/<device_id>')
def swap_page(device_id):
    return spa.render('Swap a switch')


@bp.route('/api/switch-swap/<device_id>', methods=['GET'])
def swap_plan(device_id):
    try:
        return jsonify(_plan(device_id))
    except switch_swap.SwapError as exc:
        return jsonify({'error': str(exc)}), exc.status


@bp.route('/api/switch-swap/<device_id>', methods=['POST'])
def swap(device_id):
    user = _user() or {}
    who = user.get('display_name') or user.get('username') or ''
    body = request.get_json(silent=True) or {}
    with data_lock:
        data = load_data()
        try:
            entry = switch_swap.swap(data, device_id, body, who)
        except switch_swap.SwapError as exc:
            return jsonify({'error': str(exc)}), exc.status
        save_data(data)
        name = next(d.get('name') for d in data['inventory'] if d['id'] == device_id)
    audit.record('inventory', 'Swapped switch hardware', g.get('audit_user'), name,
                 {'old_serial': entry['old_serial'], 'new_serial': entry['new_serial']})
    _note_incident(device_id, name, entry, user)
    return jsonify({'swap': entry, **_plan(device_id)})


def _note_incident(device_id, name, entry, user):
    """The switch's open incident says when the new box went in, for the timeline and the report."""
    from .. import incidents
    incident = next((i for i in incidents.list_all()
                     if i.get('switch_id') == device_id and i['status'] != 'fixed'), None)
    if not user and not current_app.extensions['auth'].enabled:
        from .incidents import _stand_in  # sign-in off: the board's shared crew account
        user = _stand_in()
    if incident is None or not user:
        return
    # Someone outside the incident's team may swap it: the audit log still has it then.
    with contextlib.suppress(incidents.IncidentError):
        incidents.update(user, incident['id'], {'note': (
            f"Swapped the hardware of {name}: serial {entry['old_serial'] or '?'} out, {entry['new_serial']} in.")})
