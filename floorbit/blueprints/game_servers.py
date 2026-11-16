"""Game servers (issue #472). Rules in floorbit/game_servers.py, docs in docs/game-servers.md.

- ``GET /game-servers``: the page.
- ``GET /api/game-servers``: every server with its last answer (up or down, players, map, ping).
- ``POST /api/game-servers``, ``PUT /api/game-servers/<id>``, ``DELETE ...``: admins set them up.
  ``rcon_password`` is write-only.
- ``POST /api/game-servers/check/<id>``: ask one server now (``games.rcon``).
- ``POST /api/game-servers/rcon/<id>``: ``{"command", "confirm"?}`` (``games.rcon``), audit-logged.
"""
from flask import Blueprint, g, jsonify, request

from .. import audit, game_servers, spa, vault

bp = Blueprint('game_servers', __name__)


def _error(exc):
    return jsonify({'error': str(exc), **exc.extra}), exc.status


@bp.route('/game-servers')
def game_servers_page():
    return spa.render('Game servers')


@bp.route('/api/game-servers', methods=['GET'])
def list_servers():
    return jsonify(game_servers.overview())


@bp.route('/api/game-servers', methods=['POST'])
@bp.route('/api/game-servers/<server_id>', methods=['PUT'])
def save_server(server_id=None):
    body = request.get_json(silent=True) or {}
    try:
        server = game_servers.save(body, server_id)
    except game_servers.GameServerError as exc:
        return _error(exc)
    except vault.VaultError as exc:
        return jsonify({'error': str(exc)}), 500
    fields = [k for k in ('name', 'game', 'host', 'port', 'query', 'rcon_port', 'rcon_password', 'clear_rcon')
              if k in body]
    audit.record('games', 'Changed a game server' if server_id else 'Added a game server', g.get('audit_user'),
                 server['name'], fields=fields)
    game_servers.poller.check(game_servers.get(server['id']))
    return jsonify(server), 200 if server_id else 201


@bp.route('/api/game-servers/<server_id>', methods=['DELETE'])
def delete_server(server_id):
    gone = game_servers.delete(server_id)
    if gone is None:
        return jsonify({'error': 'No such game server.'}), 404
    audit.record('games', 'Removed a game server', g.get('audit_user'), gone['name'])
    return jsonify({'ok': True})


@bp.route('/api/game-servers/check/<server_id>', methods=['POST'])
def check_server(server_id):
    server = game_servers.get(server_id)
    if server is None:
        return jsonify({'error': 'No such game server.'}), 404
    return jsonify({**game_servers.public(server), **game_servers.poller.check(server)})


@bp.route('/api/game-servers/rcon/<server_id>', methods=['POST'])
def rcon(server_id):
    body = request.get_json(silent=True) or {}
    command = body.get('command')
    try:
        server, answer = game_servers.run_rcon(server_id, command, confirm=bool(body.get('confirm')))
    except game_servers.GameServerError as exc:
        if exc.status in (500, 502):        # the command was meant to go out: log that it didn't
            name = (game_servers.get(server_id) or {}).get('name', server_id)
            audit.record('games', f'RCON: {game_servers.for_audit(command)}', g.get('audit_user'), name, ok=False)
        return _error(exc)
    audit.record('games', f'RCON: {game_servers.for_audit(command)}', g.get('audit_user'), server['name'])
    return jsonify({'server': server['name'], 'command': command.strip(), 'answer': answer})
