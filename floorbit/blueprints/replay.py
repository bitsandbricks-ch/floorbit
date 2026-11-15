"""Event timeline replay (issue #21): the event on the floor plan, with a time slider. See docs/replay.md.

- ``GET /replay``: the page (React).
- ``GET /api/replay?hall=<id>``: one hall's seat blocks, and what the app kept about the event:
  bandwidth and online seats from the stats reads, which seats went online or offline when, check-ins
  and incidents. Seat numbers and times only: no nicks, IPs or MACs.
- ``GET /api/replay/event?hall=<id>``: the whole event (issue #104), one frame every five minutes,
  thinned out as it gets older (floorbit/recording.py), with per-block numbers for the heatmap.
- ``GET /api/replay/event.json``: every frame of every hall, as a download.

History it uses, all kept already: the stats samples and seat changes (24 hours, floorbit/stats.py),
the check-in history (integrations/history.py) and the incident board.
"""
from flask import Blueprint, Response, current_app, jsonify, request

from .. import halls, incidents, recording, spa
from ..store import load_data
from .screen import plan

bp = Blueprint('replay', __name__)

CHECKIN_EVENTS = {'checkin': 1, 'moved': 0, 'removed': 0}   # moved: the seat it left


def _checkins():
    """[t, seat, 1|0] from the whole check-in history, without who."""
    from integrations import history
    if not history.enabled():
        return []
    out = []
    for e in history.read_all():
        on = CHECKIN_EVENTS.get(e.get('event'))
        if on is not None and e.get('seat'):
            out.append([e['ts'], str(e['seat']), on])
    return out


def _incidents(since):
    out = []
    for i in incidents.list_all():
        if since is not None and (i.get('fixed_at') or i['created_at']) < since:
            continue
        out.append({'id': i['id'], 'title': i['title'], 'seat': i.get('seat'), 'switch': i.get('switch_name'),
                    'start': i['created_at'], 'end': i.get('fixed_at')})
    return sorted(out, key=lambda i: i['start'])


@bp.route('/replay')
def replay_page():
    return spa.render('Replay')


@bp.route('/api/replay', methods=['GET'])
def replay_data():
    from ..attention import AttentionWatch
    data = load_data()
    all_halls = halls.halls(data)
    hall = halls.find(data, request.args.get('hall') or '') or all_halls[0]
    drawing, _ = plan(data, hall_id=hall['id'])
    timeline = current_app.extensions['floorbit_stats'].timeline()
    times = [s['t'] for s in timeline['samples']] + [e[0] for e in timeline['seat_events']]
    since = min(times) if times else None
    checkins = _checkins()
    times += [c[0] for c in checkins]
    found = _incidents(since)
    times += [i['start'] for i in found]
    return jsonify({
        'halls': [{'id': h['id'], 'name': h['name']} for h in all_halls],
        'hall': hall['id'],
        'drawing': drawing,
        'start': min(times) if times else None,
        'end': max(times) if times else None,
        'interval': AttentionWatch.interval(),
        **timeline,
        'checkins': checkins,
        'incidents': found,
    })


@bp.route('/api/replay/event', methods=['GET'])
def whole_event():
    data = load_data()
    all_halls = halls.halls(data)
    hall = halls.find(data, request.args.get('hall') or '') or all_halls[0]
    drawing, _ = plan(data, hall_id=hall['id'])
    seats = {c['seat'] for b in (drawing or {}).get('shapes', []) for c in b['cells']}
    names = {str(b.get('name') or '').upper() or '?' for b in (drawing or {}).get('shapes', [])}
    frames = []
    for f in recording.frames():
        frames.append({**f, 'seats': [s for s in f.get('seats') or [] if s in seats],
                       'incidents': [s for s in f.get('incidents') or [] if s in seats],
                       'blocks': {k: v for k, v in (f.get('blocks') or {}).items() if k in names}})
    return jsonify({
        'halls': [{'id': h['id'], 'name': h['name']} for h in all_halls],
        'hall': hall['id'],
        'drawing': drawing,
        'frames': frames,
        'start': frames[0]['t'] if frames else None,
        'end': frames[-1]['t'] if frames else None,
        'step': recording.STEP,
    })


@bp.route('/api/replay/event.json', methods=['GET'])
def whole_event_download():
    body = jsonify({'frames': recording.frames(), 'step': recording.STEP}).get_data()
    return Response(body, mimetype='application/json',
                    headers={'Content-Disposition': 'attachment; filename="event-replay.json"'})
