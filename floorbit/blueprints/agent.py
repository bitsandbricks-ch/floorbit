"""The local agent (issue #2). Rules in floorbit/agent_link.py, docs in docs/agent.md.

For admins (``settings.manage``):

- ``GET /settings/agents``: the page (React); ``/settings/agents/<id>``: one agent's page.
- ``GET /api/agents``: the enrolled agents, whether each is connected, and the tunnel's state.
- ``GET /api/agents/<id>/devices``: the devices it collects, their state and why one sends nothing.
- ``POST /api/agents`` ``{"name"}``: enrol one; the answer holds its key, this once.
- ``PATCH /api/agents/<id>`` ``{"tags": [ids]}``: the inventory tags it answers for (empty: every device).
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
- ``GET /api/agent/v1/captive``: ``{"done": [ip], "portal_url"}`` for its Captive Portal API
  (floorbit/captive.py); 409 while check-in is off here.
- ``POST /api/agent/v1/env-settings`` ``{"settings": {key: value}, "plugins": [id]}``: what the
  agent's environment set for plugins, taken over once where nothing is set up here (agent_plugins.py).
- ``GET /api/agent/v2/link`` (WebSocket, protocol 2): the same calls and answers as the long poll,
  over one open connection. The agent falls back to the long poll when it can't be opened.
"""
import json
import math
import threading
import time
import zlib

from flask import Blueprint, current_app, g, jsonify, request
from flask_sock import Sock
from simple_websocket import ConnectionClosed

from integrations import events

from .. import agent_clock, agent_link, audit, features, spa

bp = Blueprint('agent', __name__)
sock = Sock()
HEADER = 'Floorbit-Agent-Key'
PROTOCOL_HEADER = 'Floorbit-Agent-Protocol'
LINK_PATH = '/api/agent/v2/link'
LINK_TAKE = 5            # seconds the link waits for calls before it looks at the connection again
LINK_PING = 20           # a message at least this often, so proxies keep the connection open
LINK_IDLE = 60           # an agent silent for this long is gone: close, it reconnects
# A frozen agent or a cut line sends no close: when the agent sits on a call this long without a
# word, ask it (a ping it echoes); no word back within LINK_PROBE_WAIT and the link is dead.
LINK_PROBE = 3
LINK_PROBE_WAIT = 5


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


@bp.route('/settings/agents/<agent_id>')
def agent_page(agent_id):
    return spa.render('Local agent')


@bp.route('/api/agents', methods=['GET'])
def list_agents():
    server = current_app.config.get('FLOORBIT_VERSION') or '0'
    from .. import agent_ha, agent_updates, cluster, inventory_scope
    release = agent_updates.latest()
    # What each can do, so the pages say what falls back for an older agent (agent_ha.CAPABILITIES).
    agents = [{**a, 'outdated': agent_link.outdated(a.get('protocol')),
               'capabilities': agent_ha.capabilities(a.get('report')),
               # Where its own update stands: the newest release this Floorbit has (agent_updates.py).
               'self_update': agent_updates.status(a, release)} for a in agent_link.all_agents()]
    names = {t['id']: t['name'] for t in inventory_scope.tags(agent_link.load_data())}
    return jsonify({'agents': agents, 'connected': agent_link.tunnel.connected(),
                    'max': agent_link.MAX_AGENTS, 'server_version': server, 'protocol': agent_link.PROTOCOL,
                    'newest_version': agent_link.newest_version(agents),
                    'agent_release': release['version'] if release else None,
                    'groups': agent_ha.groups(agents, names), 'hosted': cluster.status()})


@bp.route('/api/agents/load', methods=['GET'])
def load():
    """Every agent's work over the last hour in one answer, for the sparklines in the Local agents
    list (one request instead of one per agent): ``{"hours", "agents": {agent id: {"load": [[time,
    per minute]], "syslog": lines per minute}}}`` (agent_history.add_up)."""
    from .. import agent_demo, agent_history
    from ..database import DatabaseUnavailable
    series = {}
    try:
        for a in agent_link.all_agents():
            series[a['id']] = (agent_history.add_up(agent_demo.history(a['id'], 1)) if a.get('demo')
                               else agent_history.load(a['id'], 1))
    except DatabaseUnavailable:
        return jsonify({'error': 'The database is not answering.', 'code': 'database_unavailable'}), 503
    return jsonify({'hours': 1, 'agents': series})


@bp.route('/api/agents/<agent_id>/history', methods=['GET'])
def history(agent_id):
    """One agent's numbers over time, for the graphs on its page (agent_history.py)."""
    if not any(a['id'] == agent_id for a in agent_link.all_agents()):
        return jsonify({'error': 'No such agent.'}), 404
    try:
        hours = max(0.25, min(float(request.args.get('hours') or 6), 48.0))
    except ValueError:
        hours = 6
    from .. import agent_demo, agent_history
    from ..database import DatabaseUnavailable
    if any(a['id'] == agent_id and a.get('demo') for a in agent_link.all_agents()):
        return jsonify({'hours': hours, 'series': agent_demo.history(agent_id, hours)})
    try:
        series = agent_history.history(agent_id, hours)
    except DatabaseUnavailable:
        return jsonify({'error': 'The database is not answering.', 'code': 'database_unavailable'}), 503
    return jsonify({'hours': hours, 'series': series})


@bp.route('/api/agents/<agent_id>/devices', methods=['GET'])
def agent_devices(agent_id):
    """The devices this agent collects, with their state and problems: its Devices tab (issue #1013)."""
    from .. import agent_devices as found
    result = found.devices_of(agent_id, current_app.extensions.get('floorbit_plugins'))
    if result is None:
        return jsonify({'error': 'No such agent.'}), 404
    return jsonify(result)


@bp.route('/api/agents', methods=['POST'])
def enrol():
    try:
        record, key = agent_link.enrol((request.get_json(silent=True) or {}).get('name'), _who())
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('settings', 'Enrolled a local agent', g.get('audit_user'), record['name'])
    events.publish('agents.changed', {})
    return jsonify({**record, 'key': key, 'image': agent_link.agent_image()}), 201


@bp.route('/api/agents/<agent_id>', methods=['PATCH'])
def change(agent_id):
    """``{"name"}``, ``{"tags": [inventory tag id]}`` and/or ``{"plugins_off": [plugin id]}``."""
    body = request.get_json(silent=True) or {}
    out = {'id': agent_id}
    try:
        if 'name' in body:
            old, name = agent_link.rename(agent_id, body['name'])
            audit.record('agents', f'Renamed a local agent: {old}', g.get('audit_user'), name, fields=['name'])
            out['name'] = name
        if 'tags' in body:
            name, tags = agent_link.set_tags(agent_id, body.get('tags') or [])
            from .. import inventory_scope
            names = {t['id']: t['name'] for t in inventory_scope.tags(agent_link.load_data())}
            audit.record('agents', 'Set the tags of a local agent: '
                         f"{', '.join(names.get(t, t) for t in tags) or 'every device'}",
                         g.get('audit_user'), name, fields=['tags'])
            out['tags'] = tags
        if 'plugins_off' in body:
            name, off = agent_link.set_plugins_off(agent_id, body.get('plugins_off'))
            audit.record('agents', f"Set the plugins a local agent leaves off: {', '.join(off) or 'none'}",
                         g.get('audit_user'), name, fields=['plugins_off'])
            out['plugins_off'] = off
            from .. import agent_plugins
            agent_plugins.reload_agents()
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    events.publish('agents.changed', {})
    return jsonify(out)


@bp.route('/api/agents/<agent_id>/rotate', methods=['POST'])
def rotate(agent_id):
    """A new key, shown once. The old one works until the agent uses the new one (24 h at most)."""
    try:
        name, key = agent_link.rotate(agent_id)
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('agents', 'Made a new key for a local agent', g.get('audit_user'), name)
    events.publish('agents.changed', {})
    return jsonify({'id': agent_id, 'name': name, 'key': key, 'image': agent_link.agent_image()})


@bp.route('/api/agents/ca.pem', methods=['GET'])
def ca_certificate():
    """The CA that signs the agents' certificates (agent_ca.py), to install on crew devices."""
    from .. import agent_ca
    try:
        pem = agent_ca.ca_pem()
    except agent_ca.CAError as exc:
        return jsonify({'error': str(exc)}), exc.status
    resp = current_app.response_class(pem, mimetype='application/x-pem-file')
    resp.headers['Content-Disposition'] = 'attachment; filename="floorbit-agents-ca.pem"'
    return resp


@bp.route('/api/agents/ca.crl', methods=['GET'])
def ca_revocations():
    """The CA's revocation list (agent_ca.py): open to everyone, since a crew device's TLS stack
    fetches it without signing in, and it holds only serial numbers."""
    from .. import agent_ca
    try:
        der = agent_ca.crl_der()
    except agent_ca.CAError as exc:
        return jsonify({'error': str(exc)}), exc.status
    resp = current_app.response_class(der, mimetype='application/pkix-crl')
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


ca_revocations._auth_public = True


@bp.route('/api/agents/<agent_id>/settings', methods=['GET'])
def settings_page(agent_id):
    """The agent's Settings tab: its settings, this agent's plugin settings, key and certificate."""
    from .. import agent_settings, i18n
    try:
        return jsonify(agent_settings.page(agent_id, lang=i18n.language(request.headers.get('Accept-Language'))))
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status


@bp.route('/api/agents/<agent_id>/settings', methods=['PATCH'])
def settings_change(agent_id):
    """``{"settings": {key: value | null}, "plugins": {plugin id: {setting: value | null}}}``."""
    from .. import agent_plugins, agent_settings
    body = request.get_json(silent=True) or {}
    try:
        name, changed = agent_settings.update(agent_id, body.get('settings'), body.get('plugins'))
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    if changed:
        audit.record('agents', f"Changed a local agent's settings: {', '.join(changed)}", g.get('audit_user'), name,
                     fields=changed)
        agent_plugins.reload_agents()
        events.publish('agents.changed', {})
    from .. import i18n
    return jsonify(agent_settings.page(agent_id, lang=i18n.language(request.headers.get('Accept-Language'))))


@bp.route('/api/agents/<agent_id>/roll', methods=['POST'])
def roll_key(agent_id):
    """The agent fetches a new key itself, at once when it is connected (no key to copy)."""
    from .. import agent_plugins, agent_settings
    try:
        name = agent_settings.ask_roll(agent_id)
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('agents', 'Asked a local agent to fetch a new key', g.get('audit_user'), name)
    agent_plugins.reload_agents()
    events.publish('agents.changed', {})
    return jsonify(agent_settings.state(agent_id))


@bp.route('/api/agents/roll', methods=['POST'])
def roll_all_keys():
    """Every agent fetches a new key."""
    from .. import agent_plugins, agent_settings
    names = [agent_settings.ask_roll(a['id']) for a in agent_link.all_agents()]
    if names:
        audit.record('agents', 'Asked every local agent to fetch a new key', g.get('audit_user'), ', '.join(names))
        agent_plugins.reload_agents()
        events.publish('agents.changed', {})
    return jsonify({'asked': len(names)})


@bp.route('/api/agents/<agent_id>/cert', methods=['POST'])
def new_cert(agent_id):
    """The agent asks for a new certificate at its next config pull."""
    from .. import agent_plugins, agent_settings
    try:
        if not agent_settings.values(agent_id).get('cert_names'):
            return jsonify({'error': 'List the names this agent is reached by (cert_names) before it can get a '
                                     'certificate.'}), 400
        name = agent_settings.ask_cert(agent_id)
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('agents', 'Asked a local agent to fetch a new certificate', g.get('audit_user'), name)
    agent_plugins.reload_agents()
    events.publish('agents.changed', {})
    return jsonify(agent_settings.state(agent_id))


@bp.route('/api/agents/<agent_id>/identity/reset', methods=['POST'])
def reset_identity(agent_id):
    """Forget the agent's pinned key (agent_identity.py): its next hello enrols a new one. For a
    machine whose state was lost; a key that may have leaked calls for revoking the agent instead."""
    from .. import agent_identity, agent_settings
    try:
        name = agent_identity.reset(agent_id)
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('agents', "Reset a local agent's identity", g.get('audit_user'), name)
    events.publish('agents.changed', {})
    return jsonify(agent_settings.state(agent_id))


@bp.route('/api/agents/<agent_id>', methods=['DELETE'])
def revoke(agent_id):
    from .. import public_cert
    record = next((a for a in agent_link.load_data().get(agent_link.KEY) or [] if a.get('id') == agent_id), None)
    try:
        name = agent_link.revoke(agent_id)
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('settings', 'Revoked a local agent', g.get('audit_user'), name)
    if public_cert.agent_revoked(record):
        audit.record('agents', "The agents' Let's Encrypt certificate is replaced: a revoked agent had its key",
                     g.get('audit_user'), name)
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


def _target():
    """The path and query as the agent signed them."""
    query = request.query_string.decode('latin-1')
    return request.path + (f'?{query}' if query else '')


def _identity_refusal(key):
    """Why this request's signature doesn't hold for the key's agent (agent_identity.py), or None.
    Checked before the key, so a refused request doesn't count as the agent being seen."""
    from .. import agent_identity
    m = agent_link.KEY_RE.match(str(key or '').strip())
    if not m:
        return None                      # the key check refuses it
    agent_id = m.group(1)
    identity = agent_identity.pinned(agent_id)
    header = request.headers.get(agent_identity.SIGNATURE_HEADER)
    g.agent_signed = False
    if identity is None:
        if request.path in agent_identity.OPEN_PATHS:
            return None
        return agent_identity.IdentityError(
            'The agent has no pinned key yet: it enrols one at hello. Update the agent if it does not.', 'enrol')
    try:
        agent_identity.verify(agent_id, identity, request.method, _target(), header, request.get_data())
    except agent_identity.IdentityError as exc:
        if request.path == agent_identity.OPEN_PATHS[0] and exc.code in ('clock', 'unsigned'):
            return None                  # hello still answers, with the time and what it needs
        return exc
    g.agent_signed = True
    return None


def _agent(reachable=True):
    """``reachable``: this request shows calls can reach the agent (its link, or the long poll).
    Its answers, syslog, flows and reports don't: a stopping agent posts its last answers and its
    backlog after its link closed, and counting that kept it "connected" for a minute while calls
    to it waited and failed. A long-polling agent shows it by asking for calls.

    Both factors: the request's signature by the agent's pinned key, then its bearer key."""
    refusal = _identity_refusal(request.headers.get(HEADER))
    if refusal is not None:
        g.agent_refusal = refusal
        return None
    return agent_link.check(request.headers.get(HEADER), request.headers.get('Floorbit-Agent-Version'),
                            request.remote_addr, protocol=(request.headers.get(PROTOCOL_HEADER) or '1').strip(),
                            # An unsigned hello (enrolling, or a clock to put right) can't take calls.
                            reachable=reachable and bool(g.get('agent_signed')))


MAX_UNZIPPED = 32 * 1024 * 1024    # as MAX_CONTENT_LENGTH: a small gzip body can't unpack into more


class BodyRefused(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def _agent_body():
    """The JSON an agent posted, gzipped or not. Gzip saves the event's uplink most on syslog
    batches and inventories; agents use it once hello says it's understood. A body that unpacks
    past MAX_UNZIPPED or isn't JSON is refused out loud: read as empty, the agent took the answer
    as done and its lines were lost without a word on either side."""
    raw = request.get_data(cache=False)
    if (request.headers.get('Content-Encoding') or '').lower() == 'gzip':
        unzip = zlib.decompressobj(wbits=31)
        try:
            raw = unzip.decompress(raw, MAX_UNZIPPED)
        except zlib.error:
            raise BodyRefused('The agent sent a broken gzip body.', 400) from None
        if unzip.unconsumed_tail:
            raise BodyRefused('The agent sent more than 32 MB at once; send it in parts.', 413)
    try:
        body = json.loads(raw or b'{}')
    except ValueError:
        raise BodyRefused('The agent sent a body that is not JSON.', 400) from None
    if not isinstance(body, dict):
        raise BodyRefused('The agent sent a body that is not JSON.', 400)
    return body


@bp.errorhandler(BodyRefused)
def _body_refused(exc):
    print(f'[agent] refused a post to {request.path}: {exc}')
    return jsonify({'error': str(exc)}), exc.status


def _refused():
    refusal = g.get('agent_refusal')
    if refusal is not None:
        print(f'[agent] refused {request.method} {request.path}: {refusal}')
        return jsonify({'error': str(refusal), 'code': refusal.code}), 401
    return jsonify({'error': 'The agent key is wrong or was revoked. Enrol the agent again.'}), 401


@bp.route('/api/agent/v1/hello', methods=['GET'])
def hello():
    agent = _agent()
    if agent is None:
        return _refused()
    events.publish('agents.changed', {})
    from .. import agent_identity
    identity = agent_identity.pinned(agent['id'])
    return jsonify({'name': agent['name'], 'server_version': current_app.config.get('FLOORBIT_VERSION') or '0',
                    'encodings': ['gzip'], 'protocol': agent_link.PROTOCOL,
                    'protocols': list(agent_link.PROTOCOLS), 'link': LINK_PATH,
                    # What the agent needs to sign its next requests: enrol (no pin yet), or renew.
                    'identity': {'pinned': identity is not None, 'signed': bool(g.get('agent_signed')),
                                 'not_after': (identity or {}).get('not_after'),
                                 'renew_days': agent_identity.RENEW_DAYS,
                                 'path': agent_identity.OPEN_PATHS[1]}})


@bp.route('/api/agent/v1/identity', methods=['POST'])
def identity():
    """``{"csr"}``: the agent's own key, signed by the agents CA as its client certificate and
    pinned (agent_identity.py). The first one wins; a later one must be signed by the pinned key."""
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    from .. import agent_ca, agent_identity
    try:
        pem, record, first = agent_identity.enrol(agent['id'], _agent_body().get('csr'), bool(g.get('agent_signed')))
    except agent_identity.IdentityError as exc:
        return jsonify({'error': str(exc), 'code': exc.code}), 409
    except agent_ca.CAError as exc:
        return jsonify({'error': str(exc)}), exc.status
    if first:
        audit.record('agents', "Pinned a local agent's own key", 'agent', agent['name'],
                     fields=[record['spki'][:32]])
    events.publish('agents.changed', {})
    return jsonify({'cert': pem, 'not_after': record['not_after'], 'fingerprint': record['spki'][:32]})


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
    agent = _agent(reachable=False)
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
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    receiver = current_app.extensions.get('floorbit_syslog')
    if receiver is None or not features.on('syslog'):
        return jsonify({'error': 'Syslog is turned off on this Floorbit (Settings > Features).'}), 409
    body = _agent_body()
    lines = body.get('lines') if isinstance(body.get('lines'), list) else []
    dropped = body.get('dropped') if isinstance(body.get('dropped'), int) else 0
    taken = receiver.relay(agent['name'], lines[:SYSLOG_BATCH], dropped=dropped,
                          offset=agent_clock.offset(agent))
    if lines:
        agent_link.tunnel.relayed(agent['id'], 'syslog', taken)
    return jsonify({'taken': taken, 'received': min(len(lines), SYSLOG_BATCH)})


# What the Traffic page reads from a summary (floorbit/flows/aggregate.py), with the most of each list.
FLOW_KEYS = {'updated': None, 'flows': None, 'exporters': 50, 'mix_hour': None, 'mix_day': None, 'series': 120,
             'areas': 200, 'services': 25, 'other_services': None, 'seats': 5000, 'anomalies': 200,
             'min_seats': None, 'p2p_peers': None, 'burst_pps': None, 'retention_days': None, 'raw': None,
             'templates_missing': None, 'errors': None, 'refused': None}


# What each row of a list needs before a page reads it (the rest is checked by type in _flow_value).
_NUM = (int, float)
FLOW_ROWS = {'services': {'name': str, 'bytes': _NUM, 'seats': _NUM},
             'anomalies': {'id': str, 'kind': str, 'first_seen': _NUM, 'last_seen': _NUM, 'title': str, 'detail': str},
             'areas': {'area': str, 'bytes': _NUM}, 'seats': {'seat': str, 'bytes': _NUM}, 'series': {'t': _NUM},
             'exporters': {'address': str}}
FLOW_MAPS = {'mix_hour', 'mix_day', 'raw'}


def _traffic_off():
    return jsonify({'error': 'Traffic is turned off on this Floorbit (Settings > Features).'}), 409


@bp.route('/api/agent/v1/seats', methods=['GET'])
def flow_seats():
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    if not features.on('traffic'):
        return _traffic_off()
    from ..flows import seat_maps
    seat_of, area_of = seat_maps()
    return jsonify({'seat_of': seat_of, 'area_of': area_of})


@bp.route('/api/agent/v1/captive', methods=['GET'])
def captive():
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    from integrations import config
    if not config.get_bool('CHECKIN_ENABLED', False):
        return jsonify({'error': 'Check-in is turned off on this Floorbit.'}), 409
    from .. import captive as captive_mod
    name = agent.get('name') if isinstance(agent, dict) else getattr(agent, 'name', None)
    return jsonify(captive_mod.answer(current_app, agent=name))


@bp.route('/api/agent/v1/seat-walk', methods=['POST'])
def seat_walk_hello():
    """The agent saw the crew's laptop with a walk-through code: ``{"token", "ip"}`` (seat_walk.py)."""
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    from .. import seat_walk
    body = _agent_body()
    if not seat_walk.agent_said_hello(body.get('token'), body.get('ip'), agent.get('name')):
        return jsonify({'error': 'That walk-through code is unknown, used or too old.'}), 404
    return jsonify({'ok': True})


@bp.route('/api/agent/v1/env-settings', methods=['POST'])
def env_settings():
    """What the agent's environment set for plugins before Settings > Plugins decided alone
    (``{"settings": {key: value}, "plugins": [id]}``), taken over once (agent_plugins.import_env)."""
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    body = _agent_body()
    from .. import agent_plugins
    return jsonify(agent_plugins.import_env(agent, body.get('settings'), body.get('plugins')))


@bp.route('/api/agent/v1/key', methods=['POST'])
def fetch_key():
    """An agent asked to roll its key fetches the new one (agent_settings.take_roll) and keeps it in
    its own state folder. The answer is the only place the new key is ever shown."""
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    from .. import agent_settings
    key = agent_settings.take_roll(agent['id'])
    if key is None:
        return jsonify({'error': 'No new key was asked for this agent.'}), 409
    audit.record('agents', 'A local agent fetched its new key', 'agent', agent['name'])
    events.publish('agents.changed', {})
    resp = jsonify({'key': key})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@bp.route('/api/agent/v1/cert', methods=['POST'])
def sign_cert():
    """The agent's signing request (its key stays on the agent), signed for the names on its page."""
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    from .. import agent_ca, agent_settings, public_cert
    body = _agent_body()
    if body.get('public') is True:
        # The tenant's Let's Encrypt certificate, its key sealed to this agent's own (public_cert.py).
        try:
            found = public_cert.bundle(agent['id'], body.get('csr'))
        except public_cert.PublicCertError as exc:
            return jsonify({'error': str(exc)}), 409
        audit.record('agents', "Gave a local agent the agents' Let's Encrypt certificate", 'agent', agent['name'])
        events.publish('agents.changed', {})
        resp = jsonify(found)
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    try:
        pem = agent_settings.issue_cert(agent['id'], body.get('csr'))
    except agent_ca.CAError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('agents', 'Signed a certificate for a local agent', 'agent', agent['name'])
    events.publish('agents.changed', {})
    return jsonify({'cert': pem})


@bp.route('/api/agent/v1/report', methods=['POST'])
def report():
    """The agent's own numbers, from an agent on the long poll (on the link they come as a
    ``{"type": "report"}`` message). Shown on the Local agents page."""
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    agent_link.tunnel.report(agent['id'], _agent_body().get('report'))
    return jsonify({'ok': True})


@bp.route('/api/agent/v1/flows', methods=['POST'])
def flows():
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    if not features.on('traffic'):
        return _traffic_off()
    body = _agent_body()
    if not take_flow_summary(agent, body.get('snapshot')):
        return jsonify({'error': 'snapshot is missing'}), 400
    return jsonify({'ok': True})


def _flow_scalar(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) and abs(value) < 2 ** 63 else None
    if isinstance(value, str):
        return value[:300]
    return None


def _flow_value(value, depth=0):
    """A summary value in the shapes the Traffic, Games and wall pages read: numbers, short texts,
    rows of those, and one level of maps inside a row (a seat's ``mix``). An agent of another
    version, or a broken one, must not leave a list where a page adds up numbers."""
    if isinstance(value, list):
        if depth:
            return None
        return [row for row in (_flow_value(v, 1) for v in value[:5000]) if isinstance(row, dict)]
    if isinstance(value, dict):
        # A row is depth 1, so a map inside it (a seat's mix) is depth 2.
        if depth > 2:
            return None
        out = {}
        for k, v in list(value.items())[:500]:
            v = _flow_value(v, depth + 1) if isinstance(v, dict) else _flow_scalar(v)
            if v is not None:
                out[str(k)[:120]] = v
        return out
    return _flow_scalar(value)

def take_flow_summary(agent, snap):
    """Keep an agent's traffic summary (also the Traffic from the hall plugin's). False: not one."""
    if not isinstance(snap, dict) or not isinstance(snap.get('updated'), (int, float)):
        return False
    clean = {}
    for key, most in FLOW_KEYS.items():
        if key in snap:
            value = _flow_value(snap[key])
            if key in FLOW_ROWS:
                needs = FLOW_ROWS[key]
                value = value if isinstance(value, list) else []
                value = [r for r in value if all(isinstance(r.get(k), kind) and not isinstance(r.get(k), bool)
                                                 for k, kind in needs.items())]
            elif key in FLOW_MAPS and not isinstance(value, dict):
                value = {}
            elif key not in FLOW_MAPS and isinstance(value, (list, dict)):
                value = None
            clean[key] = value[:most] if most and isinstance(value, list) else value
    from .. import agent_ha
    if agent_ha.standby_with_primary(agent['id'], time.time()):
        # Two agents of one group: the primary's summary stands; a standby's would replace it with part of it.
        agent_link.tunnel.relayed(agent['id'], 'flows', 0)
        return True
    # The hosted clock decides whether the summary is stale, not the agent's.
    clean['updated'] = time.time()
    clean['agent'] = agent['name']
    from ..flows import store
    store.publish(clean)
    agent_link.tunnel.relayed(agent['id'], 'flows', 1)
    return True


def _pin_of(agent_id):
    from .. import agent_identity
    return (agent_identity.pinned(agent_id) or {}).get('spki')


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
    pin = _pin_of(agent['id'])
    gone = threading.Event()
    released = []
    heard = [time.monotonic()]       # when the agent last said anything
    release_lock = threading.Lock()

    def release():
        # Whichever side sees the link end first: the reader at once, the sender within LINK_TAKE.
        with release_lock:
            if released:
                return
            released.append(True)
        if agent_link.tunnel.unlinked(agent['id']):
            events.publish('agents.changed', {})

    def read():
        try:
            while not gone.is_set():
                raw = ws.receive(timeout=LINK_IDLE)
                if raw is None:
                    break
                heard[0] = time.monotonic()
                agent_link.tunnel.seen_on_link(agent['id'])
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
            release()

    agent_link.tunnel.linked(agent['id'])
    threading.Thread(target=read, name='agent-link-read', daemon=True).start()
    events.publish('agents.changed', {})
    ws.send(json.dumps({'type': 'hello', 'name': agent['name'], 'protocol': agent_link.PROTOCOL}))
    quiet_since = time.monotonic()
    probed = None
    try:
        while not gone.is_set():
            if not agent_link.enrolled(agent['id']) or _pin_of(agent['id']) != pin:
                # Revoked, or its identity reset, while connected: neither key holds, so neither does this link.
                ws.close(reason=1008, message='The agent was revoked, or its identity reset.')
                break
            now = time.monotonic()
            if probed is not None and heard[0] >= probed:
                probed = None
            if probed is not None and now - probed > LINK_PROBE_WAIT:
                release()                # pages stop waiting now, whatever the close below does
                ws.close(reason=1001, message='The agent stopped answering.')
                break
            if (probed is None and now - heard[0] > LINK_PROBE
                    and agent_link.tunnel.waiting_on(agent['id'], LINK_PROBE, now)):
                ws.send(json.dumps({'type': 'ping'}))
                probed = quiet_since = now
            if now - heard[0] < LINK_IDLE:
                agent_link.tunnel.seen_on_link(agent['id'])
            calls = agent_link.tunnel.take(1 if probed is not None else LINK_TAKE, agent=agent['id'])
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
        release()


# The agent has no session: its key is checked in each view (auth's guard leaves these paths alone).
for _view in (hello, calls, answers, syslog, flow_seats, captive, seat_walk_hello, flows, link, report,
              env_settings, fetch_key, sign_cert, identity):
    _view._auth_public = True
# After _auth_public is set: the route's wrapper copies the attribute.
sock.route(LINK_PATH, bp=bp)(link)
