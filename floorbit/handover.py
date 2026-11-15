"""Shift handover (issue #33). See docs/handover.md.

The outgoing shift sees what happened since the last handover, writes a note for the next shift and
hands over. What happened is put together from what Floorbit already keeps:

- incidents still open, and the ones opened and fixed since;
- switch outages since (the stats store's switch events);
- what is wrong right now (the Problems list);
- changes from the audit log: port actions, settings, the floor plan, power, plugins and accounts.

Each handover is kept in data.json under ``handover`` (the newest ``MAX_KEPT``): when, who, the note
and the counts. The next summary starts where the last handover ended.
"""
import threading
import time
import uuid
from datetime import datetime

from .store import load_data, save_data

KEY = 'handover'
MAX_KEPT = 100
MAX_NOTE = 4000
FIRST_SHIFT_HOURS = 8          # with no handover yet, look back this far
MAX_CHANGES = 100
# Audit areas a shift wants to know about. Incidents have their own section; sign-ins are noise.
CHANGE_AREAS = ('ports', 'settings', 'floor plan', 'power', 'plugins', 'accounts', 'security', 'check-in', 'gear')

_lock = threading.Lock()


class HandoverError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def history(data=None):
    data = data if data is not None else load_data()
    raw = data.get(KEY) if isinstance(data.get(KEY), list) else []
    return sorted((h for h in raw if isinstance(h, dict) and h.get('at')), key=lambda h: -h['at'])


def last(data=None):
    found = history(data)
    return found[0] if found else None


def since_default(now, data=None):
    previous = last(data)
    return previous['at'] if previous else now - FIRST_SHIFT_HOURS * 3600


def _stamp(text):
    try:
        return datetime.strptime(text, '%Y-%m-%dT%H:%M:%S%z').timestamp()
    except (TypeError, ValueError):
        return None


def _changes(since):
    from . import audit
    entries, _ = audit.read(limit=2000)
    out = []
    for e in entries:   # newest first
        at = _stamp(e.get('time'))
        if at is None or at < since:
            if at is not None:
                break
            continue
        if e.get('area') in CHANGE_AREAS and e.get('ok', True):
            out.append({'at': at, 'user': e.get('user'), 'area': e['area'], 'action': e.get('action'),
                        'target': e.get('target')})
        if len(out) >= MAX_CHANGES:
            break
    return out


def _outages(switch_events, since, now):
    """Per switch: when it went down after ``since``, and when (if) it came back."""
    out, open_ = [], {}
    for t, sid, name, status in sorted(switch_events or [], key=lambda e: e[0]):
        if status == 'offline':
            open_[sid] = {'switch_id': sid, 'name': name, 'down_at': t, 'back_at': None}
        elif status == 'online' and sid in open_:
            item = open_.pop(sid)
            item['back_at'] = t
            if t >= since:
                out.append(item)
    out.extend(v for v in open_.values())
    for item in out:
        item['down_s'] = round((item['back_at'] or now) - item['down_at'])
    return sorted(out, key=lambda o: -o['down_at'])


def _where(i):
    if i.get('seat'):
        return {'kind': 'seat', 'name': i['seat']}
    if i.get('circuit_id'):
        return {'kind': 'circuit', 'name': i.get('circuit_name') or i['circuit_id']}
    return {'kind': 'switch', 'name': i.get('switch_name') or i.get('switch_id')}


def _incident(i, match):
    return {'id': i['id'], 'title': i.get('title'), 'where': _where(i), 'status': i.get('status'),
            'assignee': i.get('assignee'), 'team': i.get('team'), 'created_at': i.get('created_at'),
            'fixed_at': i.get('fixed_at'), 'match': match.get(i.get('seat') or '')}


def summary(switch_events, problems_now, since=None, now=None):
    from . import incidents, tournament
    now = time.time() if now is None else now
    data = load_data()
    since = since_default(now, data) if since is None else since
    match = tournament.match_seats(data)
    items = incidents.list_all()
    still_open = [_incident(i, match) for i in items if i.get('status') != 'fixed']
    still_open.sort(key=lambda i: (not i['match'], i['status'] != 'open', i['created_at'] or 0))
    fixed = [_incident(i, match) for i in items if i.get('status') == 'fixed' and (i.get('fixed_at') or 0) >= since]
    opened = sum(1 for i in items if (i.get('created_at') or 0) >= since)
    outages = [o for o in _outages(switch_events, since, now) if o['down_at'] >= since or o['back_at'] is None
               or o['back_at'] >= since]
    changes = _changes(since)
    return {
        'since': since, 'now': now, 'previous': last(data),
        'incidents': {'open': still_open, 'opened': opened, 'fixed': fixed},
        'outages': outages,
        'problems': problems_now,
        'changes': changes,
        'counts': {'open': len(still_open), 'opened': opened, 'fixed': len(fixed), 'outages': len(outages),
                   'still_down': sum(1 for o in outages if o['back_at'] is None), 'changes': len(changes),
                   'problems': problems_now.get('down', 0) + problems_now.get('warn', 0)},
    }


def hand_over(user, note, counts, since, now=None):
    note = str(note or '').strip()[:MAX_NOTE]
    now = time.time() if now is None else now
    with _lock:
        data = load_data()
        record = {'id': uuid.uuid4().hex[:12], 'at': now, 'since': since, 'by': user, 'note': note,
                  'counts': counts}
        data[KEY] = [record, *history(data)[:MAX_KEPT - 1]]
        save_data(data)
        return record


def discord_message(record, summary_, public_url='', username='Floorbit'):
    """One embed for the crew channel: the counts, what is still open, and the note."""
    c = record['counts']
    lines = [f"**{c['open']}** incidents open ({c['opened']} new, {c['fixed']} fixed this shift)",
             f"**{c['outages']}** switch outages" + (f", **{c['still_down']}** still down" if c['still_down'] else ''),
             f"**{c['problems']}** problems right now, **{c['changes']}** changes in the audit log"]
    top = summary_['incidents']['open'][:5]
    if top:
        lines.append('')
        lines.extend(f"• {i['title']} ({i['where']['name']})" + (f" · {i['assignee']}" if i['assignee'] else '')
                     for i in top)
    embed = {'title': f"🔁 Shift handover by {record['by'] or 'someone'}"[:250], 'description': '\n'.join(lines)[:3500],
             'color': 0x22C3E6,
             'timestamp': datetime.fromtimestamp(record['at']).astimezone().isoformat()}
    if record['note']:
        embed['fields'] = [{'name': 'Note for the next shift', 'value': record['note'][:1000]}]
    if public_url:
        embed['url'] = public_url.rstrip('/') + '/handover'
    return {'username': username, 'embeds': [embed], 'allowed_mentions': {'parse': []}}
