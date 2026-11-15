"""Switch commands (issue #94). The rules live in floorbit/commands.py.

- ``GET /api/commands``: the templates this account may run, the switches and whether a login is needed.
- ``POST /api/commands/run``: ``{template, switches, port?, username?, password?, confirm?}``. Show
  templates need ``ports.act``, change templates ``commands.change`` and ``confirm: true``.
- ``PUT /api/commands/templates/<id>``, ``DELETE ...``: an admin's own templates (``settings.manage``).
"""
from flask import Blueprint, current_app, g, jsonify, request

from .. import audit, commands, spa

bp = Blueprint('commands', __name__)


def _registry():
    return current_app.extensions['floorbit_plugins']


def _can(permission):
    from auth import current_user, roles  # late: auth imports floorbit while it loads
    if not current_app.extensions['auth'].enabled:
        return True
    user = current_user()
    return bool(user and roles.can(user, permission))


@bp.app_context_processor
def command_flags():
    try:
        return {'commands_on': commands.plugin(_registry()) is not None}
    except Exception:  # noqa: BLE001 - a nav link must never break a page
        return {'commands_on': False}


@bp.route('/commands')
def commands_page():
    return spa.render('Switch commands')


@bp.route('/api/commands', methods=['GET'])
def command_info():
    out = commands.info(_registry(), _can('commands.change'))
    out['may_edit'] = _can('settings.manage')
    return jsonify(out)


@bp.route('/api/commands/run', methods=['POST'])
def run():
    body = request.get_json(silent=True) or {}
    account = g.get('audit_user') or '?'
    try:
        tpl, port, sent, results = commands.run(_registry(), account, body, _can('commands.change'))
    except commands.CommandError as exc:
        if exc.confirm:
            return jsonify({'error': str(exc), 'confirm': True}), 409
        audit.record('commands', 'Ran switch commands: failed', user=g.get('audit_user'),
                     target=str(body.get('template') or '?')[:40], ok=False)
        return jsonify({'error': str(exc)}), exc.status
    for r in results:
        # One line per switch; the output never goes to the audit log.
        audit.record('commands', f"Ran {tpl['label']}" + ('' if r['ok'] else ': failed'), user=g.get('audit_user'),
                     target=r['switch'] + (f' {port}' if port else ''), ok=r['ok'])
    return jsonify({'template': tpl['id'], 'label': tpl['label'], 'kind': tpl['kind'], 'port': port or None,
                    'commands': sent, 'results': results})


@bp.route('/api/commands/templates/<tid>', methods=['PUT', 'DELETE'])
def template(tid):
    if not _can('settings.manage'):
        return jsonify({'error': 'Only an admin changes templates.'}), 403
    if request.method == 'DELETE':
        if not commands.delete_template(tid):
            return jsonify({'error': 'No such template of yours.'}), 404
        audit.record('commands', 'Deleted command template', user=g.get('audit_user'), target=tid)
        return jsonify({'ok': True})
    try:
        tpl = commands.save_template({**(request.get_json(silent=True) or {}), 'id': tid})
    except commands.CommandError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('commands', 'Saved command template', user=g.get('audit_user'), target=tid,
                 fields=['label', 'kind', 'commands'])
    return jsonify({'template': tpl})
