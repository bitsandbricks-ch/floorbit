"""Pre-flight check board (issue #35). Rules in floorbit/preflight.py.

- ``GET /preflight``: the page (React).
- ``GET /api/preflight``: the last result of each group of checks.
- ``POST /api/preflight/run`` ``{"group": "switches"|"uplinks"|"services"}``: run one group, or all
  without a group. Needs ``incidents.work``: it asks the monitoring source and the health plugins now.
- ``GET /api/preflight.pdf?tz=<minutes>``: the result to print and sign.
"""
from flask import Blueprint, Response, current_app, jsonify, request

from integrations import events

from .. import preflight, spa

bp = Blueprint('preflight', __name__)


@bp.route('/preflight')
def preflight_page():
    return spa.render('Pre-flight check')


@bp.route('/api/preflight', methods=['GET'])
def board():
    return jsonify(preflight.board())


@bp.route('/api/preflight/run', methods=['POST'])
def run():
    from auth import current_user  # late: auth imports floorbit while it loads
    group = (request.get_json(silent=True) or {}).get('group')
    if group and group not in preflight.GROUPS:
        return jsonify({'error': f"Group must be one of: {', '.join(preflight.GROUPS)}."}), 400
    user = current_user() or {}
    result = preflight.run([group] if group else list(preflight.GROUPS),
                           user.get('display_name') or user.get('username'),
                           current_app.extensions.get('floorbit_health'))
    events.publish('preflight.changed', {'group': group})
    return jsonify(result)


@bp.route('/api/preflight.pdf', methods=['GET'])
def printout():
    try:
        tz = int(request.args.get('tz', '0'))
    except ValueError:
        tz = 0
    name = current_app.extensions['floorbit_settings'].get('theme.name') or ''
    body = preflight.pdf_report(preflight.board(), name, max(-840, min(840, tz)))
    headers = {'Content-Disposition': 'inline; filename="preflight-check.pdf"', 'Cache-Control': 'no-store'}
    return Response(body, mimetype='application/pdf', headers=headers)
