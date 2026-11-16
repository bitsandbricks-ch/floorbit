"""Buttons in the crew's Discord channel (issue #32). The bridge itself is integrations/crew.py.

- ``POST /api/discord/interactions``: Discord's Interactions Endpoint. No session: Discord calls it
  server to server. Each request must carry a valid Ed25519 signature for the app's public key
  (``DISCORD_APP_PUBLIC_KEY``), so only Discord can call it.

"Mute … for 1 h" under a switch or service alert mutes it for an hour (issues #272, #274).
Slash commands (``/status``, ``/seat``, ``/switch``) and their autocomplete are answered by
floorbit/discord_commands.py.

A click acts as the Floorbit account linked to the clicking Discord user, with that account's
permissions, exactly as if they had clicked on the incident board. Clicks from another server or
channel than the crew's are refused.
"""
import time

from flask import Blueprint, current_app, jsonify, request

from integrations import crew, events

from .. import audit, discord_commands, incidents

bp = Blueprint('crew', __name__)

PING, COMMAND, COMPONENT, AUTOCOMPLETE, MODAL_SUBMIT = 1, 2, 3, 4, 5
PONG, MESSAGE, CHOICES, MODAL = 1, 4, 8, 9
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
    """An answer only the asker sees; ``text`` may be discord_commands.answer() with buttons. In the
    asker's Discord language when Floorbit has it (German), else English."""
    data = text if isinstance(text, dict) else {'content': text}
    from .. import i18n
    data = i18n.translate_payload(data, str((request.get_json(silent=True) or {}).get('locale') or ''))
    return jsonify({'type': MESSAGE, 'data': {**data, 'content': data['content'][:1900], 'flags': EPHEMERAL,
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
    if body.get('type') in (COMMAND, AUTOCOMPLETE):
        return _command(body)
    if body.get('type') not in (COMPONENT, MODAL_SUBMIT):
        return _say('Floorbit only knows its own buttons.')
    return _click(body)


interactions._auth_public = True   # what auth.public_endpoint sets: Discord signs it instead


def _command(body):
    """A slash command (floorbit/discord_commands.py). Any channel on the crew's server."""
    auth = current_app.extensions['auth']
    provider = auth.providers.get('discord')
    guild = getattr(provider, 'guild_id', '') if provider else ''
    if guild and str(body.get('guild_id') or '') != guild:
        if body.get('type') == AUTOCOMPLETE:
            return jsonify({'type': CHOICES, 'data': {'choices': []}})
        return _say('Floorbit only answers on its own server.')
    if body.get('type') == AUTOCOMPLETE:
        return jsonify({'type': CHOICES, 'data': {'choices': discord_commands.autocomplete(body)}})
    answer = discord_commands.handle(body)
    return _say(answer if answer is not None else 'Floorbit does not know this command.')


def _click(body):
    auth = current_app.extensions['auth']
    provider = auth.providers.get('discord')
    guild = getattr(provider, 'guild_id', '') if provider else ''
    if guild and str(body.get('guild_id') or '') != guild:
        return _say('This button only works on the crew server.')
    message = body.get('message') or {}
    in_channel = crew.channel_id() in (str(body.get('channel_id') or ''), str(message.get('channel_id') or ''))
    # Buttons on a bot answer (#416) live on an ephemeral message only its asker sees, in any channel.
    on_answer = bool(int(message.get('flags') or 0) & EPHEMERAL)
    if not (in_channel or on_answer):
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
    if action == 'mute':
        return _mute(user, incident_id)
    if action == 'report':
        return _report(body, user, incident_id)
    change = {'assignee': user['username']} if action == 'take' else {'status': 'fixed'}
    try:
        incident = incidents.update(user, incident_id, change)
    except incidents.IncidentError as exc:
        return _say(str(exc))
    events.publish('incident.changed', {'id': incident['id'], 'status': incident['status']})
    label = 'Took an incident from Discord' if action == 'take' else 'Marked an incident fixed from Discord'
    audit.record('incidents', label, user=user['username'], target=incident_id)
    return _say('You have it. Notes go on the incident board.' if action == 'take' else 'Marked fixed. Thanks!')


def _report(body, user, seat):
    """"Report a problem" under a /seat answer: a one-line form, then the same as /incident report."""
    from auth import roles
    if not roles.can(user, 'incidents.work'):
        return _say('Reporting from Discord needs a Floorbit account that works incidents.')
    if body.get('type') == COMPONENT:
        return jsonify({'type': MODAL, 'data': discord_commands.report_modal(seat)})
    return _say(discord_commands.report(user, seat, discord_commands.modal_value(body)))


def _mute(user, switch_id):
    """"Mute … for 1 h" under a switch-offline alert (issue #272), as that person on the Problems page."""
    from auth import roles
    if not roles.can(user, 'incidents.work'):
        return _say('Muting needs a Floorbit account that works incidents.')
    from integrations import alerting

    from .. import inventory
    from ..store import load_data
    if switch_id.startswith('health:'):
        # A service on the health wall (issue #274), muted under the same key as on the Problems page.
        wall = current_app.extensions.get('floorbit_health')
        check = next((c for c in (wall.snapshot()['checks'] if wall else [])
                      if alerting.service_key(c['id']) == switch_id), None)
        if not check:
            return _say('That service is not on the health wall any more.')
        key, name, label = switch_id, check['name'], 'Muted service alerts from Discord'
    else:
        device = next((d for d in inventory.devices(load_data(), include_hidden=True) if d['id'] == switch_id), None)
        if not device:
            return _say('That switch is not on the floor plan any more.')
        key, name, label = device['id'], device['name'], 'Muted switch alerts from Discord'
    entry = alerting.mute(key, name, crew.MUTE_MINUTES, user['username'], 'Muted from Discord')
    audit.record('alerts', label, user=user['username'], target=name)
    events.publish('alerts.changed', {})
    until = time.strftime('%H:%M', time.localtime(entry['until']))
    return _say(f"Muted {name} until {until}. Unmute or add time on the Problems page.")
