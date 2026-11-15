"""Slash commands for the Floorbit Discord bot (the full-bot epic #407; /status is #408).

The bot answers over the same Interactions Endpoint as the crew channel's buttons
(floorbit/blueprints/crew.py), so it still needs no gateway connection. integrations/crew.py
registers ``COMMANDS`` with Discord once the bot token and the app's public key are set.

A command acts as the Floorbit account linked to the Discord user (Discord sign-in), with that
account's permissions, like a button click. Answers are ephemeral: only the person who asked sees
them, so a command in a busy channel adds no noise and shows crew detail to nobody else.
"""
from flask import current_app

GUILD_ONLY = [0]   # Discord's interaction context for a server, not a DM

COMMANDS = [
    {'name': 'status', 'type': 1, 'contexts': GUILD_ONLY,
     'description': 'How the network is doing: the state, the areas down, the latest crew update.'},
]

STATE_TEXT = {'operational': 'All systems running', 'degraded': 'Part of the network is down',
              'outage': 'Network outage', 'maintenance': 'Maintenance',
              'unknown': 'Status not available right now'}
STATE_ICON = {'operational': '🟢', 'degraded': '🟠', 'outage': '🔴', 'maintenance': '🛠️', 'unknown': '⚪'}
MAX_AREAS = 10


def linked_user(body):
    """The Floorbit account linked to the Discord user who asked, as auth.public() shows it, or None."""
    auth = current_app.extensions['auth']
    discord_user = (body.get('member') or {}).get('user') or body.get('user') or {}
    account = auth.users.find_by_identity('discord', discord_user.get('id')) if discord_user.get('id') else None
    if not account:
        return None
    from auth import public
    return public(account)


NOT_LINKED = ('Your Discord account is not linked to a Floorbit account yet. Sign in to Floorbit with '
              'Discord once, or ask an admin to add your Discord ID on the Users page.')


def handle(body):
    """The answer text for an application command, or None for a command Floorbit doesn't know."""
    name = (body.get('data') or {}).get('name')
    if name == 'status':
        return _status(linked_user(body))
    return None


def _area_name(a):
    if a.get('block'):
        return f"Seat block {a['block']}" + (f" · {a['hall']}" if a.get('hall') else '')
    return f"Hall {a['hall']}" if a.get('hall') else 'Somewhere in the hall'


def _area_line(a, crew):
    seats = a.get('seats')
    bits = [f"rows {a['rows']}" if a.get('rows') else '', f"{seats} seat{'s' if seats != 1 else ''}" if seats else '']
    if crew and a.get('switches'):
        bits.append('switches: ' + ', '.join(a['switches']))
    rest = ' · '.join(b for b in bits if b)
    return f"• {_area_name(a)}" + (f" ({rest})" if rest else '')


def _status(user):
    from auth import roles

    from .blueprints import status_page as page
    crew = bool(user) and roles.can(user, 'incidents.work')
    if not crew and not page.page_on():
        # Without an account the bot says only what the public status page would.
        return NOT_LINKED if not user else 'The network status needs a Floorbit account that works incidents.'
    s = page._now(show_names=crew)
    lines = [f"{STATE_ICON.get(s['state'], '')} **{STATE_TEXT.get(s['state'], s['state'])}**"]
    if s.get('since'):
        lines[0] += f" since <t:{int(s['since'])}:t>"
    if s['areas']:
        lines.append('Affected:')
        lines += [_area_line(a, crew) for a in s['areas'][:MAX_AREAS]]
        if len(s['areas']) > MAX_AREAS:
            lines.append(f"…and {len(s['areas']) - MAX_AREAS} more")
    if s.get('recovered'):
        lines.append('Back up recently: ' + ', '.join(_area_name(a) for a in s['recovered'][:MAX_AREAS]))
    if s['updates']:
        u = s['updates'][0]
        where = f" · {u['area']}" if u.get('area') else ''
        lines.append(f"Latest update (<t:{int(u['at'])}:t>{where}): {u['text']}")
    if crew and s.get('override'):
        lines.append(f"State set by hand by {s['override'].get('by') or 'someone'}.")
    return '\n'.join(lines)
