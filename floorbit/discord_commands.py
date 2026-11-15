"""Slash commands for the Floorbit Discord bot (the full-bot epic #407: /status #408, /seat and /switch #410, /incident and /jobs #412).

The bot answers over the same Interactions Endpoint as the crew channel's buttons
(floorbit/blueprints/crew.py), so it still needs no gateway connection. integrations/crew.py
registers ``COMMANDS`` with Discord once the bot token and the app's public key are set.

A command acts as the Floorbit account linked to the Discord user (Discord sign-in), with that
account's permissions, like a button click. Answers are ephemeral: only the person who asked sees
them, so a command in a busy channel adds no noise and shows crew detail to nobody else.
"""
from flask import current_app

GUILD_ONLY = [0]   # Discord's interaction context for a server, not a DM

SUB = 1           # Discord's option type for a subcommand
STRING = 3        # Discord's option type for text
MAX_CHOICES = 25  # Discord's limit for autocomplete answers
MAX_LISTED = 20   # seats listed under a switch

COMMANDS = [
    {'name': 'status', 'type': 1, 'contexts': GUILD_ONLY,
     'description': 'How the network is doing: the state, the areas down, the latest crew update.'},
    {'name': 'seat', 'type': 1, 'contexts': GUILD_ONLY,
     'description': 'One seat: online or not, its switch port and open incidents.',
     'options': [{'type': STRING, 'name': 'seat', 'description': 'Seat number, e.g. A-12', 'required': True,
                  'autocomplete': True, 'max_length': 20}]},
    {'name': 'switch', 'type': 1, 'contexts': GUILD_ONLY,
     'description': 'One switch: up or down, and which of its seats are offline.',
     'options': [{'type': STRING, 'name': 'name', 'description': 'Switch name, e.g. sw-a-01', 'required': True,
                  'autocomplete': True, 'max_length': 64}]},
    {'name': 'incident', 'type': 1, 'contexts': GUILD_ONLY, 'description': 'The incident board from Discord.',
     'options': [
         {'type': SUB, 'name': 'report', 'description': 'File an incident for a seat.', 'options': [
             {'type': STRING, 'name': 'seat', 'description': 'Seat number, e.g. A-12', 'required': True,
              'autocomplete': True, 'max_length': 20},
             {'type': STRING, 'name': 'problem', 'description': 'What is wrong, in a few words', 'required': True,
              'max_length': 120}]},
         {'type': SUB, 'name': 'take', 'description': 'Take an open incident.', 'options': [
             {'type': STRING, 'name': 'incident', 'description': 'Start typing a seat or a few words',
              'required': True, 'autocomplete': True, 'max_length': 100}]},
         {'type': SUB, 'name': 'fixed', 'description': 'Mark an incident fixed.', 'options': [
             {'type': STRING, 'name': 'incident', 'description': 'Start typing a seat or a few words',
              'required': True, 'autocomplete': True, 'max_length': 100},
             {'type': STRING, 'name': 'note', 'description': 'What you did (optional)', 'max_length': 500}]},
     ]},
    {'name': 'jobs', 'type': 1, 'contexts': GUILD_ONLY, 'description': 'The incidents you have, oldest first.'},
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


def _options(body):
    """The options given, flattened through a subcommand: ({name: value}, subcommand or None)."""
    opts = (body.get('data') or {}).get('options') or []
    sub = None
    if opts and opts[0].get('type') == SUB:
        sub, opts = opts[0].get('name'), opts[0].get('options') or []
    return {o.get('name'): str(o.get('value') or '').strip() for o in opts}, sub


def _option(body, name):
    return _options(body)[0].get(name, '')


def _crew(user):
    from auth import roles
    return bool(user) and roles.can(user, 'incidents.work')


def handle(body):
    """The answer text for an application command, or None for a command Floorbit doesn't know."""
    name = (body.get('data') or {}).get('name')
    if name == 'status':
        return _status(linked_user(body))
    if name in ('seat', 'switch'):
        user = linked_user(body)
        if not user:
            return NOT_LINKED
        if not _crew(user):
            return f'/{name} needs a Floorbit account that works incidents.'
        return _seat(_option(body, 'seat')) if name == 'seat' else _switch(_option(body, 'name'))
    if name in ('incident', 'jobs'):
        user = linked_user(body)
        if not user:
            return NOT_LINKED
        if name == 'jobs':
            return _jobs(user)
        given, sub = _options(body)
        return _incident(user, sub, given)
    return None


def autocomplete(body):
    """Choices for the option being typed: seat numbers, switch names or open incidents, for crew only."""
    data = body.get('data') or {}
    opts = data.get('options') or []
    if opts and opts[0].get('type') == SUB:
        opts = opts[0].get('options') or []
    focused = next((o for o in opts if o.get('focused')), None)
    user = linked_user(body)
    if not focused or not _crew(user):
        return []
    typed = str(focused.get('value') or '').strip().lower()
    if focused.get('name') == 'incident':
        return _incident_choices(user, typed)
    if focused.get('name') == 'seat':
        from . import incidents
        names = sorted(incidents.seat_numbers(), key=_natural)
    elif focused.get('name') == 'name' and data.get('name') == 'switch':
        from . import inventory
        from .store import load_data
        names = sorted({d['name'] for d in inventory.devices(load_data()) if d.get('name')}, key=_natural)
    else:
        return []
    hits = [n for n in names if n.lower().startswith(typed)] or [n for n in names if typed in n.lower()]
    return [{'name': n, 'value': n} for n in hits[:MAX_CHOICES]]


def _natural(name):
    import re
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', name)]


def _link(path):
    from integrations.crew import _public_url
    base = _public_url()
    return f"\n<{base}{path}>" if base else ''


def _ago(at):
    return f"<t:{int(at)}:R>" if at else ''


STATE_DOT = {'online': '🟢 online', 'offline': '🔴 offline', 'unknown': '⚪ no reading'}


def _seat(seat):
    # States, ports and incidents only: never nicks, IPs or MACs, which stay in Floorbit.
    from . import seat_view
    if not seat:
        return 'Which seat? For example `/seat A-12`.'
    d = seat_view.details(seat, people=False, crew=False)
    if d is None:
        return f'There is no seat {seat.upper()} on the floor plan.'
    head = f"**Seat {d['seat']}** · {STATE_DOT.get(d['state'], d['state'])}"
    if d.get('bps'):
        head += f" · {d['bps'] / 1e6:.1f} Mbit/s"
    lines = [head, f"Port: {d['switch']} {d['port']}" if d.get('switch') else 'Port: not known yet']
    if d['incidents']:
        lines.append('Open incidents:')
        lines += [f"• {i['title']} ({i['status']}, {_ago(i['created_at'])})" for i in d['incidents']]
    else:
        lines.append('No open incidents.')
    lines += [f"⚠️ {a['title']}" for a in d.get('attention') or []]
    fixed = d.get('fixed_before') or {}
    if fixed.get('count'):
        times = 'once' if fixed['count'] == 1 else f"{fixed['count']} times"
        lines.append(f"Fixed here before: {times} (last: {fixed['last']['title']})")
    return '\n'.join(lines) + _link(f"/plan?seat={d['seat']}")


def _switch(name):
    from . import seat_view
    if not name:
        return 'Which switch? For example `/switch sw-a-01`.'
    d = seat_view.switch(name)
    if d is None:
        return f'There is no switch called {name} on the floor plan.'
    icon = {'online': '🟢 up', 'offline': '🔴 down'}.get(d['status'], '⚪ no reading')
    head = f"**{d['name']}** · {icon}" + (f" since <t:{int(d['since'])}:t>" if d.get('since') else '')
    if d.get('model'):
        head += f" · {d['model']}"
    lines = [head]
    if d['seats']:
        lines.append(f"Seats online: {d['online']} of {len(d['seats'])}")
        off = [r for r in d['seats'] if r['state'] != 'online']
        if off:
            listed = ', '.join(f"{r['seat']} ({r['port']})" for r in off[:MAX_LISTED])
            more = f" and {len(off) - MAX_LISTED} more" if len(off) > MAX_LISTED else ''
            lines.append(f"Not online: {listed}{more}")
    else:
        lines.append('No seats known on this switch yet.')
    return '\n'.join(lines) + _link(f"/plan?switch={d['name']}")


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
    from .blueprints import status_page as page
    crew = _crew(user)
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


# ── incidents ─────────────────────────────────────────────────────────────────
MAX_JOBS = 15


def _where_text(i):
    return f"seat {i['seat']}" if i.get('seat') else i.get('switch_name') or i.get('circuit_name') or 'somewhere'


def _incident_choices(user, typed):
    from . import incidents
    mine = [i for i in incidents.list_all() if i.get('status') != 'fixed' and incidents.can_work(user, i)]
    mine.sort(key=lambda i: i.get('created_at') or 0)
    hits = [i for i in mine if not typed or typed in f"{_where_text(i)} {i['title']}".lower()]
    return [{'name': f"{_where_text(i)} · {i['title']} ({i['status']})"[:100], 'value': i['id']}
            for i in hits[:MAX_CHOICES]]


def _changed(incident, action, user, label):
    from integrations import events

    from . import audit
    events.publish('incident.changed', {'id': incident['id'], 'status': incident['status'], 'action': action})
    audit.record('incidents', label, user=user['username'], target=incident.get('seat') or incident['id'])


def _incident(user, sub, given):
    from . import dispatch, incidents
    try:
        if sub == 'report':
            incident = incidents.create(user, {'seat': given.get('seat'), 'title': given.get('problem')},
                                        source='discord')
            _changed(incident, 'created', user, 'Filed an incident from Discord')
            dispatch.send_new(incident)
            return f"Filed: {_where_text(incident)} · {incident['title']}. It is on the incident board." \
                + _link('/incidents')
        ref = given.get('incident', '')
        if not incidents.get(ref):
            return 'Pick the incident from the list Discord shows while you type.'
        if sub == 'take':
            incident = incidents.update(user, ref, {'assignee': user['username']})
            _changed(incident, 'changed', user, 'Took an incident from Discord')
            return f"You have it: {_where_text(incident)} · {incident['title']}."
        if sub == 'fixed':
            incident = incidents.update(user, ref, {'status': 'fixed', 'note': given.get('note') or ''})
            _changed(incident, 'changed', user, 'Marked an incident fixed from Discord')
            return f"Marked fixed: {_where_text(incident)} · {incident['title']}. Thanks!"
    except incidents.IncidentError as exc:
        return str(exc)
    return 'Floorbit does not know this command.'


def _jobs(user):
    from . import incidents
    mine = [i for i in incidents.list_all()
            if i.get('assignee') == user['username'] and i.get('status') != 'fixed']
    if not mine:
        return 'You have no incidents right now. `/incident take` picks one up.'
    mine.sort(key=lambda i: i.get('created_at') or 0)
    lines = [f"**Your incidents** ({len(mine)})"]
    lines += [f"• {_where_text(i)} · {i['title']} ({_ago(i.get('created_at'))})" for i in mine[:MAX_JOBS]]
    if len(mine) > MAX_JOBS:
        lines.append(f"…and {len(mine) - MAX_JOBS} more")
    return '\n'.join(lines) + _link('/jobs')
