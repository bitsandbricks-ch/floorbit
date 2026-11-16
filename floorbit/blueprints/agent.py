"""The local agent (issue #2). Rules in floorbit/agent_link.py, docs in docs/agent.md.

For admins (``settings.manage``):

- ``GET /settings/agents``: the page (React).
- ``GET /api/agents``: the enrolled agents, whether each is connected, and the tunnel's state.
- ``POST /api/agents`` ``{"name"}``: enrol one; the answer holds its key, this once.
- ``PATCH /api/agents/<id>`` ``{"halls": [ids]}``: the halls it answers for (empty: every hall).
- ``DELETE /api/agents/<id>``: revoke it.

For the agent, with its key in ``Floorbit-Agent-Key`` (no session, no browser):

- ``GET /api/agent/v1/hello``: checks the key; ``{"name", "server_version"}``.
- ``GET /api/agent/v1/calls?wait=25``: the calls waiting for it (a long poll).
- ``POST /api/agent/v1/answers`` ``{"answers": [{"id", "ok", "result", "error"}]}``.
- ``POST /api/agent/v1/syslog`` ``{"lines": [{"raw", "from", "at"}], "dropped"}``: syslog the agent
  received on the event network; 409 while the syslog feature is off here.
- ``GET /api/agent/v1/seats``: ``{"seat_of": {ip: seat}, "area_of": {seat: area}}`` for its flow
  collector; 409 while the traffic feature is off here.
- ``POST /api/agent/v1/flows`` ``{"snapshot"}``: its flow collector's summary (aggregates only).
- ``GET /api/agent/v2/link`` (WebSocket, protocol 2): the same calls and answers as the long poll,
  over one open connection. The agent falls back to the long poll when it can't be opened.
"""
import json
import threading
import time
import zlib

from flask import Blueprint, current_app, g, jsonify, request
from flask_sock import Sock
from simple_websocket import ConnectionClosed

from integrations import events

from .. import agent_link, audit, features, spa

bp = Blueprint('agent', __name__)
sock = Sock()
HEADER = 'Floorbit-Agent-Key'
PROTOCOL_HEADER = 'Floorbit-Agent-Protocol'
LINK_PATH = '/api/agent/v2/link'
LINK_TAKE = 5            # seconds the link waits for calls before it looks at the connection again
LINK_PING = 20           # a message at least this often, so proxies keep the connection open
LINK_IDLE = 60           # an agent silent for this long is gone: close, it reconnects


@bp.record_once
def _socket_options(state):
    # WebSocket pings under the usual 60 s proxy idle timeouts; answers can be large inventories.
    state.app.config.setdefault('SOCK_SERVER_OPTIONS', {'ping_interval': 25, 'max_message_size': 32 * 1024 * 1024})


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


@bp.route('/settings/agents')
def agents_page():
    return spa.render('Local agents')


@bp.route('/api/agents', methods=['GET'])
def list_agents():
    server = current_app.config.get('FLOORBIT_VERSION') or '0'
    agents = [{**a, 'outdated': agent_link.outdated(a.get('protocol'))} for a in agent_link.all_agents()]
    return jsonify({'agents': agents, 'connected': agent_link.tunnel.connected(),
                    'max': agent_link.MAX_AGENTS, 'server_version': server, 'protocol': agent_link.PROTOCOL})


@bp.route('/api/agents', methods=['POST'])
def enrol():
    try:
        record, key = agent_link.enrol((request.get_json(silent=True) or {}).get('name'), _who())
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('settings', 'Enrolled a local agent', g.get('audit_user'), record['name'])
    events.publish('agents.changed', {})
    return jsonify({**record, 'key': key}), 201


@bp.route('/api/agents/<agent_id>', methods=['PATCH'])
def set_halls(agent_id):
    body = request.get_json(silent=True) or {}
    try:
        name, halls = agent_link.set_halls(agent_id, body.get('halls', []))
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('agents', f"Set the halls of a local agent: {', '.join(halls) or 'every hall'}",
                 g.get('audit_user'), name, fields=['halls'])
    events.publish('agents.changed', {})
    return jsonify({'id': agent_id, 'halls': halls})


@bp.route('/api/agents/<agent_id>', methods=['DELETE'])
def revoke(agent_id):
    try:
        name = agent_link.revoke(agent_id)
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('settings', 'Revoked a local agent', g.get('audit_user'), name)
    events.publish('agents.changed', {})
    return jsonify({'ok': True})


@bp.before_request
def _same_protocol():
    """An agent speaking another protocol gets one clear answer instead of odd failures later.
    No header means protocol 1: every agent before the header was added spoke it."""
    if not request.path.startswith('/api/agent/'):
        return None
    spoken = (request.headers.get(PROTOCOL_HEADER) or '1').strip()
    if spoken not in {str(p) for p in agent_link.PROTOCOLS}:
        return jsonify({'error': f'This Floorbit speaks agent protocol {agent_link.PROTOCOL}, the agent {spoken[:10]}. '
                                 'Update the agent (or this Floorbit) so they match.',
                        'protocol': agent_link.PROTOCOL}), 426
    if request.path == LINK_PATH:
        # Checked before the upgrade, so a wrong key gets a plain 401 the agent can read.
        g.link_agent = _agent()
        if g.link_agent is None:
            return _refused()
    return None


def _agent():
    return agent_link.check(request.headers.get(HEADER), request.headers.get('Floorbit-Agent-Version'),
                            request.remote_addr, protocol=(request.headers.get(PROTOCOL_HEADER) or '1').strip())


MAX_UNZIPPED = 32 * 1024 * 1024    # as MAX_CONTENT_LENGTH: a small gzip body can't unpack into more


def _agent_body():
    """The JSON an agent posted, gzipped or not ({} when it isn't JSON). Gzip saves the event's
    uplink most on syslog batches and inventories; agents use it once hello says it's understood."""
    raw = request.get_data(cache=False)
    if (request.headers.get('Content-Encoding') or '').lower() == 'gzip':
        unzip = zlib.decompressobj(wbits=31)
        try:
            raw = unzip.decompress(raw, MAX_UNZIPPED)
        except zlib.error:
            return {}
        if unzip.unconsumed_tail:
            return {}
    try:
        body = json.loads(raw or b'{}')
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _refused():
    return jsonify({'error': 'The agent key is wrong or was revoked. Enrol the agent again.'}), 401


@bp.route('/api/agent/v1/hello', methods=['GET'])
def hello():
    agent = _agent()
    if agent is None:
        return _refused()
    events.publish('agents.changed', {})
    return jsonify({'name': agent['name'], 'server_version': current_app.config.get('FLOORBIT_VERSION') or '0',
                    'encodings': ['gzip'], 'protocol': agent_link.PROTOCOL,
                    'protocols': list(agent_link.PROTOCOLS), 'link': LINK_PATH})


@bp.route('/api/agent/v1/calls', methods=['GET'])
def calls():
    agent = _agent()
    if agent is None:
        return _refused()
    try:
        wait = float(request.args.get('wait') or agent_link.MAX_WAIT)
    except ValueError:
        wait = agent_link.MAX_WAIT
    return jsonify({'calls': agent_link.tunnel.take(wait, agent=agent['id'])})


@bp.route('/api/agent/v1/answers', methods=['POST'])
def answers():
    agent = _agent()
    if agent is None:
        return _refused()
    body = _agent_body()
    items = body.get('answers') if isinstance(body.get('answers'), list) else []
    taken = sum(1 for a in items[:100] if isinstance(a, dict)
                and agent_link.tunnel.answer(a.get('id'), a.get('ok'), a.get('result'), a.get('error'),
                                                     agent=agent['id']))
    return jsonify({'taken': taken})


SYSLOG_BATCH = 2000


@bp.route('/api/agent/v1/syslog', methods=['POST'])
def syslog():
    agent = _agent()
    if agent is None:
        return _refused()
    receiver = current_app.extensions.get('floorbit_syslog')
    if receiver is None or not features.on('syslog'):
        return jsonify({'error': 'Syslog is turned off on this Floorbit (Settings > Features).'}), 409
    body = _agent_body()
    lines = body.get('lines') if isinstance(body.get('lines'), list) else []
    dropped = body.get('dropped') if isinstance(body.get('dropped'), int) else 0
    taken = receiver.relay(agent['name'], lines[:SYSLOG_BATCH], dropped=dropped)
    if lines:
        agent_link.tunnel.relayed(agent['id'], 'syslog', taken)
    return jsonify({'taken': taken, 'received': min(len(lines), SYSLOG_BATCH)})


# What the Traffic page reads from a summary (floorbit/flows/aggregate.py), with the most of each list.
FLOW_KEYS = {'updated': None, 'flows': None, 'exporters': 50, 'mix_hour': None, 'mix_day': None, 'series': 120,
             'areas': 200, 'services': 25, 'other_services': None, 'seats': 5000, 'anomalies': 200,
             'min_seats': None, 'p2p_peers': None, 'burst_pps': None, 'retention_days': None, 'raw': None,
             'templates_missing': None, 'errors': None}


def _traffic_off():
    return jsonify({'error': 'Traffic is turned off on this Floorbit (Settings > Features).'}), 409


@bp.route('/api/agent/v1/seats', methods=['GET'])
def flow_seats():
    agent = _agent()
    if agent is None:
        return _refused()
    if not features.on('traffic'):
        return _traffic_off()
    from ..flows import seat_maps
    seat_of, area_of = seat_maps()
    return jsonify({'seat_of': seat_of, 'area_of': area_of})


@bp.route('/api/agent/v1/report', methods=['POST'])
def report():
    """The agent's own numbers, from an agent on the long poll (on the link they come as a
    ``{"type": "report"}`` message). Shown on the Local agents page."""
    agent = _agent()
    if agent is None:
        return _refused()
    agent_link.tunnel.report(agent['id'], _agent_body().get('report'))
    return jsonify({'ok': True})


@bp.route('/api/agent/v1/flows', methods=['POST'])
def flows():
    agent = _agent()
    if agent is None:
        return _refused()
    if not features.on('traffic'):
        return _traffic_off()
    body = _agent_body()
    snap = body.get('snapshot')
    if not isinstance(snap, dict) or not isinstance(snap.get('updated'), (int, float)):
        return jsonify({'error': 'snapshot is missing'}), 400
    clean = {}
    for key, most in FLOW_KEYS.items():
        if key in snap:
            value = snap[key]
            clean[key] = value[:most] if most and isinstance(value, list) else value
    # The hosted clock decides whether the summary is stale, not the agent's.
    clean['updated'] = time.time()
    clean['agent'] = agent['name']
    from ..flows import store
    store.publish(clean, keep_locally=True)
    agent_link.tunnel.relayed(agent['id'], 'flows', 1)
    return jsonify({'ok': True})


def _link_answers(agent, message):
    items = message.get('answers') if isinstance(message.get('answers'), list) else []
    for a in items[:100]:
        if isinstance(a, dict):
            agent_link.tunnel.answer(a.get('id'), a.get('ok'), a.get('result'), a.get('error'), agent=agent['id'])


def link(ws):
    """Protocol 2: calls go out as ``{"type": "calls", "calls": [...]}`` the moment they are made,
    answers come back as ``{"type": "answers", "answers": [...]}``, the same items as the long poll.
    ``{"type": "ping"}`` both ways keeps it alive. Syslog and flows stay on their HTTPS posts."""
    agent = g.link_agent
    gone = threading.Event()

    def read():
        try:
            while not gone.is_set():
                raw = ws.receive(timeout=LINK_IDLE)
                if raw is None:
                    break
                agent_link.tunnel.seen(agent=agent['id'])
                try:
                    message = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if isinstance(message, dict) and message.get('type') == 'answers':
                    _link_answers(agent, message)
                elif isinstance(message, dict) and message.get('type') == 'report':
                    agent_link.tunnel.report(agent['id'], message.get('report'))
        except ConnectionClosed:
            pass
        finally:
            gone.set()

    threading.Thread(target=read, name='agent-link-read', daemon=True).start()
    events.publish('agents.changed', {})
    ws.send(json.dumps({'type': 'hello', 'name': agent['name'], 'protocol': agent_link.PROTOCOL}))
    quiet_since = time.monotonic()
    try:
        while not gone.is_set():
            if not agent_link.enrolled(agent['id']):
                # Revoked while connected: the key is no good any more, so neither is this link.
                ws.close(reason=1008, message='The agent key was revoked.')
                break
            agent_link.tunnel.seen(agent=agent['id'])
            calls = agent_link.tunnel.take(LINK_TAKE, agent=agent['id'])
            if calls and gone.is_set():
                agent_link.tunnel.give_back(calls)
                break
            if calls:
                try:
                    ws.send(json.dumps({'type': 'calls', 'calls': calls}))
                except ConnectionClosed:
                    agent_link.tunnel.give_back(calls)
                    raise
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since >= LINK_PING:
                ws.send(json.dumps({'type': 'ping'}))
                quiet_since = time.monotonic()
    finally:
        gone.set()


# The agent has no session: its key is checked in each view (auth's guard leaves these paths alone).
for _view in (hello, calls, answers, syslog, flow_seats, flows, link, report):
    _view._auth_public = True
# After _auth_public is set: the route's wrapper copies the attribute.
sock.route(LINK_PATH, bp=bp)(link)
