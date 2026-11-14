"""Buttons in the crew's Discord channel (issue #32). The bridge itself is integrations/crew.py.

- ``POST /api/discord/interactions``: Discord's Interactions Endpoint. No session: Discord calls it
  server to server. Each request must carry a valid Ed25519 signature for the app's public key
  (``DISCORD_APP_PUBLIC_KEY``), so only Discord can call it.

A click acts as the Floorbit account linked to the clicking Discord user, with that account's
permissions, exactly as if they had clicked on the incident board. Clicks from another server or
channel than the crew's are refused.
"""
import time

from flask import Blueprint, current_app, jsonify, request

from integrations import crew, events

from .. import audit, incidents

bp = Blueprint('crew', __name__)

PING, COMPONENT = 1, 3
PONG, MESSAGE = 1, 4
EPHEMERAL = 64
MAX_SKEW = 300            # seconds; an older signed request is a replay


def verify(key_hex, signature_hex, timestamp, body):
    """True when Discord signed ``timestamp + body`` with the app's key."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex))
        key.verify(bytes.fromhex(signature_hex), timestamp.encode() + body)
    except (ValueError, TypeError, InvalidSignature):
        return False
    return True


def _say(text):
    return jsonify({'type': MESSAGE, 'data': {'content': text[:1900], 'flags': EPHEMERAL,
                                               'allowed_mentions': {'parse': []}}})


@bp.route('/api/discord/interactions', methods=['POST'])
def interactions():
    key = crew.public_key()
    if not key:
        return jsonify({'error': 'Discord buttons are not set up.'}), 404
    stamp = request.headers.get('X-Signature-Timestamp', '')
    if not verify(key, request.headers.get('X-Signature-Ed25519', ''), stamp, request.get_data()):
        return jsonify({'error': 'Bad signature.'}), 401
    try:
        if abs(time.time() - int(stamp)) > MAX_SKEW:
            return jsonify({'error': 'Too old.'}), 401
    except ValueError:
        return jsonify({'error': 'Bad timestamp.'}), 401
    body = request.get_json(silent=True) or {}
    if body.get('type') == PING:
        return jsonify({'type': PONG})
    if body.get('type') != COMPONENT:
        return _say('Floorbit only knows its own buttons.')
    return _click(body)


interactions._auth_public = True   # what auth.public_endpoint sets: Discord signs it instead


def _click(body):
    auth = current_app.extensions['auth']
    provider = auth.providers.get('discord')
    guild = getattr(provider, 'guild_id', '') if provider else ''
    if guild and str(body.get('guild_id') or '') != guild:
        return _say('This button only works on the crew server.')
    channel = str(body.get('channel_id') or '')
    if channel != crew.channel_id() and str((body.get('message') or {}).get('channel_id') or '') != crew.channel_id():
        return _say('This button only works in the crew channel.')
    found = crew.parse_custom_id((body.get('data') or {}).get('custom_id'))
    if not found:
        return _say('Floorbit does not know this button.')
    action, incident_id = found
    discord_user = (body.get('member') or {}).get('user') or body.get('user') or {}
    account = auth.users.find_by_identity('discord', discord_user.get('id')) if discord_user.get('id') else None
    if not account:
        return _say('Your Discord account is not linked to a Floorbit account yet. Sign in to Floorbit with '
                    'Discord once, or ask an admin to add your Discord ID on the Users page.')
    from auth import public
    user = public(account)
    change = {'assignee': user['username']} if action == 'take' else {'status': 'fixed'}
    try:
        incident = incidents.update(user, incident_id, change)
    except incidents.IncidentError as exc:
        return _say(str(exc))
    events.publish('incident.changed', {'id': incident['id'], 'status': incident['status']})
    label = 'Took an incident from Discord' if action == 'take' else 'Marked an incident fixed from Discord'
    audit.record('incidents', label, user=user['username'], target=incident_id)
    return _say('You have it. Notes go on the incident board.' if action == 'take' else 'Marked fixed. Thanks!')
