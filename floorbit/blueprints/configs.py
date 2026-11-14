"""Switch config backups and diffs (issue #96). The rules live in floorbit/config_backup.py.

- ``GET /configs``: the page. ``GET /api/configs``: every switch with its last copy and whether it
  changed since the baseline.
- ``POST /api/configs/backup``: ``{switches, username, password}``, back them up now with the tech's
  own login (never stored).
- ``GET /api/configs/<switch>``: its copies. ``GET /api/configs/<switch>/<id>``: one copy (``?download=1``
  as a file). ``GET /api/configs/<switch>/diff?from=&to=``: what changed (baseline to latest by default).
- ``POST /api/configs/<switch>/baseline``: ``{id}``, the copy later ones are compared with.

All need ``configs.read`` (admin and lead): configs describe the whole network, even without secrets.
"""
from flask import Blueprint, Response, current_app, g, jsonify, request

from .. import audit, commands, config_backup, ports, spa

bp = Blueprint('configs', __name__)


def _registry():
    return current_app.extensions['floorbit_plugins']


@bp.route('/configs')
def configs_page():
    return spa.render('Switch configs')


@bp.route('/api/configs', methods=['GET'])
def overview():
    registry = _registry()
    spec = commands.plugin(registry)
    switches = commands.info(registry, False)['switches']
    return jsonify({'available': spec is not None, 'plugin': spec.name if spec else None,
                    'needs_login': ports.info(registry)['needs_login'] if spec else False,
                    'switches': config_backup.overview(switches), 'keep': config_backup.keep(),
                    'max_switches': commands.MAX_SWITCHES})


@bp.route('/api/configs/backup', methods=['POST'])
def backup():
    body = request.get_json(silent=True) or {}
    account = g.get('audit_user') or '?'
    try:
        results = config_backup.backup(_registry(), account, body)
    except commands.CommandError as exc:
        audit.record('configs', 'Backed up switch config: failed', user=g.get('audit_user'), ok=False,
                     target=', '.join(str(s) for s in body.get('switches') or [])[:80] or '?')
        return jsonify({'error': str(exc)}), exc.status
    for r in results:
        what = 'Backed up switch config' + ('' if r['ok'] else ': failed')
        if r['ok'] and r.get('changed'):
            what += ' (changed)'
        audit.record('configs', what, user=g.get('audit_user'), target=r['switch'], ok=r['ok'])
    return jsonify({'results': results})


@bp.route('/api/configs/<switch>', methods=['GET'])
def history(switch):
    return jsonify(config_backup.history(switch))


@bp.route('/api/configs/<switch>/diff', methods=['GET'])
def diff(switch):
    out = config_backup.diff(switch, request.args.get('from') or None, request.args.get('to') or None)
    if out is None:
        return jsonify({'error': 'No such copies.'}), 404
    return jsonify(out)


@bp.route('/api/configs/<switch>/baseline', methods=['POST'])
def baseline(switch):
    cid = str((request.get_json(silent=True) or {}).get('id') or '')
    if not config_backup.set_baseline(switch, cid):
        return jsonify({'error': 'No such copy.'}), 404
    audit.record('configs', 'Set config baseline', user=g.get('audit_user'), target=f'{switch} {cid}')
    return jsonify({'ok': True})


@bp.route('/api/configs/<switch>/<cid>', methods=['GET'])
def copy(switch, cid):
    text = config_backup.text(switch, cid)
    if text is None:
        return jsonify({'error': 'No such copy.'}), 404
    if request.args.get('download'):
        return Response(text, mimetype='text/plain',
                        headers={'Content-Disposition': f'attachment; filename="{switch}-{cid}.cfg"'})
    return jsonify({'switch': switch, 'id': cid, 'text': text})
