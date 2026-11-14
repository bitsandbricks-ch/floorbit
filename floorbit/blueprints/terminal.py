"""The browser terminal for one switch (issue #95). The rules live in floorbit/terminal.py.

- ``GET /terminal``: the page. ``GET /api/terminal``: can a terminal open, the switches, your open ones.
- ``POST /api/terminal``: ``{switch, username, password, cols, rows}`` opens one; answers ``{id}``.
- ``GET /api/terminal/<id>/output?after=n``: output after character n, waiting up to 20 s for some.
- ``POST /api/terminal/<id>/input``: ``{data}``, what the tech typed. Each line goes to the audit log.
- ``POST /api/terminal/<id>/resize``: ``{cols, rows}``. ``DELETE /api/terminal/<id>``: close it.

Needs ``terminal.open`` (admin and lead by default). A session belongs to the account that opened it.
"""
from flask import Blueprint, current_app, g, jsonify, request

from .. import commands, spa, terminal

bp = Blueprint('terminal', __name__)


def _registry():
    return current_app.extensions['floorbit_plugins']


def _account():
    return g.get('audit_user') or '?'


def _error(exc):
    return jsonify({'error': str(exc)}), exc.status


@bp.route('/terminal')
def terminal_page():
    return spa.render('Terminal')


@bp.route('/api/terminal', methods=['GET'])
def info():
    from .. import ports
    spec = terminal.plugin(_registry())
    return jsonify({
        'available': spec is not None,
        'plugin': spec.name if spec else None,
        'needs_login': ports.info(_registry())['needs_login'] if spec else False,
        'switches': commands.info(_registry(), False)['switches'] if spec else [],
        'sessions': terminal.listing(_account()),
        'idle_minutes': terminal.idle_seconds() // 60,
        'max_minutes': terminal.max_seconds() // 60,
    })


@bp.route('/api/terminal', methods=['POST'])
def open_terminal():
    body = request.get_json(silent=True) or {}
    try:
        session = terminal.open_session(_registry(), _account(), body)
    except terminal.TerminalError as exc:
        return _error(exc)
    return jsonify({'id': session.id, 'switch': session.switch}), 201


@bp.route('/api/terminal/<sid>/output', methods=['GET'])
def output(sid):
    try:
        session = terminal.get(sid, _account())
    except terminal.TerminalError as exc:
        return _error(exc)
    after = request.args.get('after', 0, type=int) or 0
    wait = min(max(request.args.get('wait', terminal.POLL_SECONDS, type=float) or 0, 0), terminal.POLL_SECONDS)
    return jsonify(session.read(max(after, 0), wait))


@bp.route('/api/terminal/<sid>/input', methods=['POST'])
def send(sid):
    try:
        terminal.get(sid, _account()).write((request.get_json(silent=True) or {}).get('data'))
    except terminal.TerminalError as exc:
        return _error(exc)
    return jsonify({'ok': True})


@bp.route('/api/terminal/<sid>/resize', methods=['POST'])
def resize(sid):
    body = request.get_json(silent=True) or {}
    try:
        session = terminal.get(sid, _account())
        session.shell.resize(min(max(int(body.get('cols') or 120), 40), 300),
                             min(max(int(body.get('rows') or 32), 10), 120))
    except terminal.TerminalError as exc:
        return _error(exc)
    except (TypeError, ValueError):
        return jsonify({'error': 'cols and rows are numbers.'}), 400
    return jsonify({'ok': True})


@bp.route('/api/terminal/<sid>', methods=['DELETE'])
def close(sid):
    try:
        terminal.get(sid, _account()).end('Closed by the tech.')
    except terminal.TerminalError as exc:
        return _error(exc)
    return jsonify({'ok': True})
