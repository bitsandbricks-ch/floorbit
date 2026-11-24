"""The crew's walk-through check-in (floorbit/seat_walk.py, docs/seat-walk.md).

- ``GET /seat-walk``: the page (React).
- ``GET /api/seat-walk?rows=&order=``: the picked rows' seats (row ids from ``/api/seat-rows``,
  comma-separated) in walking order with the port each has
  in this event, the local agent's address and which ways of looking a port up are on.
- ``POST /api/seat-walk/hello``: a one-time code; ``ip`` at once when the page came through an agent's
  front door, else the agent URL the laptop opens with it (worked out, see seat_walk.agent_url).
  ``GET /api/seat-walk/hello/<code>``: the laptop's own IP once the agent saw it.
- ``POST /api/seat-walk/locate``: ``{"seat", "hello", "previous": {"switch", "port"}, "mac", "mac_ip",
  "run"}``: find the port the laptop the agent identified is plugged into now and keep it for the
  seat. Tries for about 20 seconds; ``retry`` says whether trying again is worth it. Or ``mac`` with
  ``mac_typed``: the crew typed the laptop's MAC, no agent needed. ``trace`` in the answer lists every
  step; with ``run`` (the page's random id) each step also goes out live as ``seat-walk.trace``.
- ``DELETE /api/seat-walk/<seat>``: forget the seat's port (a wrong one).
- ``POST /api/seat-walk/walkers``: ``{"rows", "order", "take"}``: start walking these rows (409 with
  ``held`` when someone else walks one, unless ``take``). ``PUT /api/seat-walk/walkers/<id>``:
  ``{"seat", "paused", "failed": {"seat", "why"}}``: where the walker is now (and that they still are),
  a pause, or a seat that wasn't found. ``POST .../<id>/take``: take the walk over, where it got to.
  ``DELETE``: the walk ends and is forgotten. The overview's ``hall`` lists every row with its
  progress and walker, ``walks`` every kept walk, ``me`` who asks (floorbit/seat_walkers.py, #1000,
  #1356).
- ``PUT /api/seat-walk/marks/<seat>``: ``{"mark": "broken" | "later" | "skip", "note"}``; ``DELETE``
  takes it off (floorbit/seat_marks.py).

The laptop is always identified through the local agent, also when Floorbit runs in the hall: the
agent sees the laptop's own address, Floorbit may see a proxy's or the hall's public one.

Reading needs ``seats.view`` (it names the laptop's MAC), changing ``seats.edit`` (auth/roles.py).
"""
import re

from flask import Blueprint, current_app, g, jsonify, request

from integrations import checkin, events

from .. import seat_marks, seat_walk, seat_walkers, sources, spa, switch_areas, tenancy
from ..store import load_data

bp = Blueprint('seat_walk', __name__)
RUN_RE = re.compile(r'^[A-Za-z0-9_-]{8,64}\Z')


def _registry():
    return current_app.extensions.get('floorbit_plugins')


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username') or 'crew'


def _user():
    """The signed-in account's username: the key of their own walks."""
    from auth import current_user
    return (current_user() or {}).get('username') or _who()


@bp.route('/seat-walk')
def page():
    return spa.render('Seat walk-through')


@bp.route('/api/seat-walk', methods=['GET'])
def overview():
    body = {'agent_url': seat_walk.agent_url() or None, 'through_agent': bool(checkin.attendee_ip()),
            'switch_lookup': seat_walk._ssh(_registry())[0] is not None,
            'monitoring': sources.monitoring().enabled(),
            'event': {k: tenancy.current().get(k) for k in ('id', 'name', 'status')},
            'keep_hours': seat_walk.KEEP_AFTER_END // 3600}
    marks = seat_marks.all_marks()
    walks = seat_walkers.walks()
    body['hall'] = seat_walkers.hall(load_data(), checkin.learned_ports(), marks=marks)
    body['walks'] = walks
    body['me'] = _user()
    body['marks'] = marks
    rows = [r for r in (request.args.get('rows') or '').split(',') if r.strip()]
    if rows:
        try:
            body.update(seat_walk.seats(rows[:50], request.args.get('order') or 'rows'))
        except seat_walk.WalkError as exc:
            return jsonify({'error': str(exc)}), exc.status
        failing = {}
        for w in walks:
            for seat, why in w['failed'].items():
                failing.setdefault(seat, {**why, 'who': w['who']})
        for row in body['seats']:
            row['mark'] = marks.get(row['seat'])
            row['failed'] = None if row['port'] else failing.get(row['seat'])
    return jsonify(body)


def _port(value):
    if not isinstance(value, dict) or not value.get('switch') or not value.get('port'):
        return None
    return {'switch': str(value['switch'])[:80], 'port': str(value['port'])[:48]}


@bp.route('/api/seat-walk/locate', methods=['POST'])
def locate():
    body = request.get_json(silent=True) or {}
    seat = str(body.get('seat') or '').strip().upper()[:16]
    if not seat or seat not in {s.upper() for s in checkin.known_seats(load_data)}:
        return jsonify({'error': 'That seat is not on the floor plan.'}), 400
    typed = seat_walk._mac(body.get('mac')) if body.get('mac_typed') else None
    if body.get('mac_typed') and not typed:
        return jsonify({'error': 'That is not a MAC address.'}), 400
    run = body.get('run') if RUN_RE.match(str(body.get('run') or '')) else None
    trace = seat_walk.Trace(run, seat)
    ip, agent = None, None   # a typed MAC: no address needed
    if typed:
        trace.add('macTyped', 'ok', mac=typed)
    else:
        # Always through the local agent, self-hosted or not: it sees the laptop's own address,
        # where Floorbit may see a proxy's or the hall's public one.
        said = seat_walk.hello(body.get('hello')) if body.get('hello') else None
        if not said or not said.get('ip'):
            return jsonify({'error': "The local agent hasn't seen this laptop yet. Identify it again."}), 409
        ip, agent = said['ip'], said.get('agent') or None
        trace.add('hello', 'ok', agent=agent, ip=ip)
    if ip and not checkin.ip_allowed(ip):
        return jsonify({'error': f'This laptop has {ip}, which is not in the seat networks. '
                                 'Turn off Wi-Fi and plug the cable in.', 'ip': ip}), 409
    registry = _registry()
    if seat_walk._ssh(registry)[0] is None and not sources.monitoring().enabled():
        return jsonify({'error': 'Nothing can look up switch ports: turn on SSH port actions, telemetry '
                                 'or LibreNMS, or connect a local agent.'}), 409
    previous = _port(body.get('previous'))
    # The MAC the last seat found, while the laptop still has the same IP: saves the ARP lookup.
    mac = typed or (seat_walk._mac(body.get('mac')) if body.get('mac') and body.get('mac_ip') == ip else None)
    if mac and not typed:
        trace.add('macReused', 'ok', mac=mac, ip=ip)
    result = seat_walk.locate(ip, registry, g.get('audit_user') or _who(), previous,
                              seat_walk.likely_switches(seat, previous), mac=mac, seat=seat, trace=trace)
    out = {'seat': seat, 'ip': ip, 'mac': result['mac'], 'agent': agent, 'how': result['how'], 'ms': result['ms'],
           'tries': result['tries'], 'steps': result['steps'], 'stale': result['stale'], 'found': result['found'],
           'trace': result['trace']}
    if not result['found']:
        return jsonify({**out, 'ok': False, 'retry': True})
    saved = seat_walk.save(seat, result['found'], _who())
    if isinstance(body.get('walker'), str):
        seat_walkers.found(body['walker'][:32], seat, result['found'], result['ms'])
    # The switch's area doesn't hold this seat (issue #1094): say so here, where it is found.
    drift = switch_areas.drift_for(seat, result['found']['switch'], load_data())
    return jsonify({**out, 'ok': True, 'retry': False, **saved, 'area_drift': drift})


@bp.route('/api/seat-walk/hello', methods=['POST'])
def new_hello():
    """A code for this laptop. Opened through an agent's front door, the agent already named the
    laptop's address: done at once (``ip``). Otherwise ``url``: the agent the laptop opens once."""
    try:
        token = seat_walk.new_hello(_who())
    except seat_walk.WalkError as exc:
        return jsonify({'error': str(exc)}), exc.status
    here = checkin.attendee_ip()
    if here and seat_walk.hello_here(token, here, 'front door'):
        return jsonify({'hello': token, 'ip': here})
    url = seat_walk.agent_url()
    if not url:
        return jsonify({'error': 'No laptop in the hall has reached a local agent yet. Open the check-in '
                                 'page once from a seat, or set the check-in address.'}), 409
    return jsonify({'hello': token, 'url': f'{url}/floorbit/hello/{token}'})


@bp.route('/api/seat-walk/hello/<token>', methods=['GET'])
def get_hello(token):
    said = seat_walk.hello(token)
    if said is None:
        return jsonify({'error': 'That code is unknown or too old.'}), 404
    return jsonify(said)


@bp.route('/api/seat-walk/<seat>', methods=['DELETE'])
def forget(seat):
    if not checkin.forget_port(seat.strip().upper()):
        return jsonify({'error': 'That seat has no learned port'}), 404
    seat_walkers.forget_seat(seat)
    events.publish('seat-walk.changed', {})
    return jsonify({'ok': True})


@bp.route('/api/seat-walk/marks/<seat>', methods=['PUT'])
def mark_seat(seat):
    seat = seat.strip().upper()[:16]
    if seat not in {s.upper() for s in checkin.known_seats(load_data)}:
        return jsonify({'error': 'That seat is not on the floor plan.'}), 400
    body = request.get_json(silent=True) or {}
    # Checked here with a fixed text, so no exception text reaches the answer.
    if body.get('mark') not in seat_marks.MARKS:
        return jsonify({'error': 'A seat is marked broken, later or skip.'}), 400
    mark = seat_marks.put(seat, body['mark'], body.get('note'), _who())
    events.publish('seat-walk.changed', {})
    return jsonify({'seat': seat, **mark})


@bp.route('/api/seat-walk/marks/<seat>', methods=['DELETE'])
def unmark_seat(seat):
    if not seat_marks.clear(seat.strip().upper()[:16], _who()):
        return jsonify({'error': 'That seat has no mark.'}), 404
    events.publish('seat-walk.changed', {})
    return jsonify({'ok': True})


def _walk_error(exc):
    body = {'error': str(exc)}
    if exc.held:
        body['held'] = exc.held
    return jsonify(body), exc.status


@bp.route('/api/seat-walk/walkers', methods=['POST'])
def start_walk():
    body = request.get_json(silent=True) or {}
    rows = body.get('rows') if isinstance(body.get('rows'), list) else []
    from ..seat_names import pick_rows
    try:
        pick_rows(load_data(), rows)
    except ValueError:
        return jsonify({'error': 'That row is not on the floor plan any more.'}), 404
    try:
        walker = seat_walkers.claim(rows, _who(), take=bool(body.get('take')), user=_user(),
                                    order=body.get('order') or 'rows')
    except seat_walkers.ClaimError as exc:
        return _walk_error(exc)
    events.publish('seat-walk.changed', {})
    return jsonify(walker), 201


@bp.route('/api/seat-walk/walkers/<walker_id>', methods=['PUT'])
def walker_at(walker_id):
    body = request.get_json(silent=True) or {}
    try:
        if isinstance(body.get('failed'), dict) and body['failed'].get('seat'):
            seat_walkers.failed(walker_id, body['failed']['seat'], body['failed'].get('why'), user=_user())
        if body.get('paused'):
            walker = seat_walkers.pause(walker_id, user=_user())
        else:
            walker = seat_walkers.at_seat(walker_id, body.get('seat'), user=_user())
    except seat_walkers.ClaimError as exc:
        return _walk_error(exc)
    events.publish('seat-walk.changed', {})
    return jsonify(walker)


@bp.route('/api/seat-walk/walkers/<walker_id>/take', methods=['POST'])
def take_walk(walker_id):
    try:
        walker = seat_walkers.take_over(walker_id, _who(), user=_user())
    except seat_walkers.ClaimError as exc:
        return _walk_error(exc)
    from .. import audit
    if walker.get('taken_from'):
        audit.record('check-in', 'Walk-through: walk taken over', _who(), walker['taken_from'])
    events.publish('seat-walk.changed', {})
    return jsonify(walker)


@bp.route('/api/seat-walk/walkers/<walker_id>', methods=['DELETE'])
def end_walk(walker_id):
    seat_walkers.release(walker_id)
    events.publish('seat-walk.changed', {})
    return jsonify({'ok': True})
