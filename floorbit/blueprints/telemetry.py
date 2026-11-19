"""Device telemetry (docs/telemetry.md). Rules in floorbit/telemetry/.

For senders, with the ingest token (``Authorization: Token <token>``, the InfluxDB v2 way, or the
token as the password of Basic auth, the InfluxDB v1 way), no account. Never in the URL, where
proxies log it:

- ``POST /api/telemetry/write`` and ``POST /api/telemetry/api/v2/write``: line protocol from
  Telegraf (the sidecar, or a firewall's own Telegraf pointed at ``/api/telemetry`` as its
  InfluxDB URL). Gzip is fine.

For the crew:

- ``GET /api/telemetry/series?device=&port=&metric=&hours=``: one normalised series over time.
- ``GET /api/telemetry/status``: is it collecting, where, how much.

For admins (``settings.manage``):

- ``GET /settings/telemetry``: the page (React).
- ``GET /api/settings/telemetry``: the devices (secrets left out) and the status.
- ``POST /api/settings/telemetry/targets``, ``PUT|DELETE /api/settings/telemetry/targets/<id>``.
- ``GET /api/settings/telemetry/targets/<id>/device-config``: what to paste on the device.
- ``GET|POST /api/settings/telemetry/token``: show the ingest token, or make a new one.
- ``GET /api/settings/telemetry/devices``: each device's last word and its problems.
- ``POST /api/settings/telemetry/test`` ``{"name"}``: collect from one device now, through the agent.
- ``GET /api/settings/telemetry/raw?name=``: the last lines the agent got from one device.
- ``GET /api/settings/telemetry/telegraf.conf``: Telegraf's config, secrets in it, for a
  Telegraf that doesn't run in the sidecar.

A local agent gets the devices and sends its series through the telemetry plugin's agent part
(builtin_plugins/telemetry/agent.py, docs/agent-plugins.md), not through routes here.
"""
import base64
import zlib

from flask import Blueprint, g, jsonify, request

from .. import audit, spa, telemetry, vault
from ..database import DatabaseUnavailable
from ..telemetry import state as state_mod
from ..telemetry import storage, targets, telegraf

bp = Blueprint('telemetry', __name__)
MAX_UNZIPPED = 32 * 1024 * 1024
METRICS = set(storage.PORT_METRICS) | set(storage.DEVICE_METRICS)


def _given_token():
    scheme, _, rest = (request.headers.get('Authorization') or '').strip().partition(' ')
    if scheme.lower() == 'token':
        return rest.strip()
    if scheme.lower() == 'basic':
        try:
            return base64.b64decode(rest.strip()).decode('utf-8', 'replace').partition(':')[2]
        except ValueError:
            return None
    return request.headers.get('Floorbit-Telemetry-Token')


def _body_text():
    raw = request.get_data(cache=False)
    if (request.headers.get('Content-Encoding') or '').lower() == 'gzip':
        unzip = zlib.decompressobj(wbits=31)
        try:
            raw = unzip.decompress(raw, MAX_UNZIPPED)
        except zlib.error:
            return None
        if unzip.unconsumed_tail:
            return None
    return raw.decode('utf-8', 'replace')


def write():
    try:
        good = targets.token_ok(_given_token())
    except (DatabaseUnavailable, vault.VaultError):
        return jsonify({'error': 'Telemetry cannot be checked right now.'}), 503
    if not good:
        return jsonify({'error': 'The telemetry token is wrong. See Settings > Telemetry.'}), 401
    if not telemetry.collector_here():
        return jsonify({'error': 'A local agent collects telemetry for this Floorbit: send it there.'}), 409
    text = _body_text()
    if text is None:
        return jsonify({'error': 'The body is not valid gzip.'}), 400
    telemetry.ingest(text)
    # InfluxDB answers 204, and some senders only take that as success.
    return '', 204


# Open to senders without an account (what auth.public_endpoint sets; auth imports floorbit, so
# not imported here): the token above is the check.
write._auth_public = True
for path, name in (('/api/telemetry/write', 'write'), ('/api/telemetry/api/v2/write', 'write_v2')):
    bp.add_url_rule(path, name, write, methods=['POST'])


@bp.route('/api/telemetry/series', methods=['GET'])
def series():
    device = (request.args.get('device') or '').strip()
    port = (request.args.get('port') or '').strip() or None
    metric = request.args.get('metric') or 'in_bps'
    if not device or metric not in METRICS:
        return jsonify({'error': 'Ask for a device and one of ' + ', '.join(sorted(METRICS)) + '.'}), 400
    try:
        hours = float(request.args.get('hours') or 6)
    except ValueError:
        hours = 6
    try:
        points = storage.storage().series(device, port, metric, hours)
    except DatabaseUnavailable:
        return jsonify({'error': 'The database is not answering.', 'code': 'database_unavailable'}), 503
    return jsonify({'device': device, 'port': port, 'metric': metric, 'points': points})


@bp.route('/api/telemetry/status', methods=['GET'])
def status():
    return jsonify(telemetry.status())


# ── settings ───────────────────────────────────────────────────────────────────────────────────

@bp.route('/settings/telemetry')
def telemetry_page():
    return spa.render('Telemetry')


def _devices():
    """What each configured device sent last, and why it sends nothing, for the page. While an
    agent collects, the picture lives there: asked through its link."""
    if not telemetry.collector_here():
        return _devices_on_agent()
    out = {}
    with state_mod.state._lock:
        for dev in state_mod.state.devices.values():
            out[dev.name] = {'seen': dev.seen or None, 'online': dev.online(), 'ports': len(dev.interfaces),
                             'macs': len(dev.fdb), 'arp': len(dev.arp),
                             'neighbours': len(dev.lldp) + len(dev.cdp)}
    return out


def _agent_numbers():
    """What each agent's telemetry plugin last reported: is Telegraf posting, and is it forwarded."""
    from .. import agent_plugins
    out = []
    for agent_id, row in agent_plugins.health_of('telemetry').items():
        health = row.get('health') or {}
        m = health.get('metrics') or {}
        out.append({'id': agent_id, 'name': row.get('name') or agent_id, 'connected': bool(row.get('connected')),
                    'status': health.get('status') or '', 'primary': bool(m.get('primary', 1)),
                    'points': int(m.get('points') or 0),
                    'series': int(m.get('series') or 0), 'sent': int(m.get('sent') or 0),
                    'heard': int(m.get('devices_heard') or 0), 'failing': int(m.get('devices_failing') or 0),
                    'quiet': int(m['telegraf_quiet_seconds']) if 'telegraf_quiet_seconds' in m else None,
                    'refused': int(m.get('refused_writes') or 0), 'bad_lines': int(m.get('bad_lines') or 0)})
    return sorted(out, key=lambda a: (not a['primary'], a['name']))


def _devices_on_agent():
    from .. import sources
    from ..plugins.base import PluginError
    try:
        found = sources.monitoring().devices() or []
    except PluginError:
        return {}
    out = {}
    for d in found if isinstance(found, list) else []:
        if not isinstance(d, dict) or d.get('source') != 'telemetry' or not d.get('hostname'):
            continue
        problems = [p for p in d.get('problems') or [] if isinstance(p, dict)]
        row = {'seen': d.get('seen'), 'online': bool(d.get('status')), 'problems': problems[:10]}
        # Counts only from an agent that sends them (older ones don't): the page leaves them out then.
        row.update({k: d[k] for k in ('ports', 'macs', 'arp', 'neighbours') if isinstance(d.get(k), int)})
        out[str(d['hostname'])] = row
    return out


@bp.route('/api/settings/telemetry', methods=['GET'])
def settings_view():
    seen, status = _devices(), telemetry.status()
    if not telemetry.collector_here():
        # This Floorbit's own counters stay at 0 while an agent collects: count what the agent heard.
        status.update(devices=sum(1 for d in seen.values() if d.get('seen')), points=None, agents=_agent_numbers())
        if status['agents']:
            status['points'] = sum(a['points'] for a in status['agents'])
    return jsonify({'targets': targets.listing(), 'inventory': targets.inventory_listing(),
                    'seen': seen, 'status': status,
                    'drivers': list(targets.DRIVERS), 'platforms': list(targets.PLATFORMS),
                    'kinds': list(targets.KINDS), 'fdb_modes': list(targets.FDB_MODES),
                    'ports': {'traps': 162, 'mdt': telegraf.MDT_PORT}})


def _save(target_id=None):
    try:
        entry = targets.save(request.get_json(silent=True), g.get('audit_user'), target_id)
    except targets.TargetError as exc:
        return jsonify({'error': str(exc)}), exc.status
    except vault.VaultError as exc:
        return jsonify({'error': str(exc)}), 500
    name = entry['name']
    label = f'Changed telemetry from {name}' if target_id else f'Added telemetry from {name}'
    audit.record('telemetry', label, g.get('audit_user'), ', '.join(entry['drivers']))
    _tell_agents()
    return jsonify(entry), 200 if target_id else 201


def _tell_agents():
    """Agents collecting for this Floorbit pick up the change now instead of within a minute."""
    from .. import agent_link, agent_plugins
    if agent_link.active():
        agent_plugins.reload_agents()


@bp.route('/api/settings/telemetry/devices', methods=['GET'])
def devices_view():
    """Each device's last word and its problems: what a device's Telemetry view shows."""
    return jsonify({'devices': _devices()})


def _ask_agents(op, name):
    """Ask the agents' telemetry part ``op`` about one device: the first one that collects from it
    answers. (answer, agent name) or a Flask error reply."""
    from flask import current_app

    from .. import agent_plugins
    from ..plugins.base import PluginError
    if telemetry.collector_here():
        message = 'Test now and raw data need a local agent: none collects for this Floorbit.'
        return None, (jsonify({'error': message}), 409)
    spec = current_app.extensions['floorbit_plugins'].specs.get('telemetry')
    if spec is None:
        return None, (jsonify({'error': 'The Telemetry plugin is missing.'}), 404)
    try:
        answers = agent_plugins.ask(spec, 'call', op, {'name': name})
    except PluginError as exc:
        return None, (jsonify({'error': str(exc)}), 502)
    # An agent that doesn't collect from it answers {ok: False, error}; one that does has points or lines.
    good = [a for a in answers if isinstance(a.get('result'), dict)
            and ('points' in a['result'] or a['result'].get('known'))]
    if good:
        return good[0], None
    errors = [a.get('error') or (a.get('result') or {}).get('error') for a in answers]
    return None, (jsonify({'error': f'No local agent collects from {name}.',
                           'detail': '; '.join(e for e in errors if e)[:500]}), 404)


def _device_name():
    body = request.get_json(silent=True) if request.method == 'POST' else request.args
    name = str((body or {}).get('name') or '').strip()
    return name[:120]


@bp.route('/api/settings/telemetry/test', methods=['POST'])
def test_device():
    """Collect from one device now, through the agent, and say what came back or why nothing did."""
    name = _device_name()
    if not name:
        return jsonify({'error': 'Which device?'}), 400
    answer, error = _ask_agents('test', name)
    if error:
        return error
    audit.record('telemetry', f'Tested telemetry from {name}', g.get('audit_user'), answer['name'])
    return jsonify({**answer['result'], 'agent': answer['name']})


@bp.route('/api/settings/telemetry/raw', methods=['GET'])
def raw_lines():
    """The last lines the agent got from one device, as Telegraf sent them."""
    name = _device_name()
    if not name:
        return jsonify({'error': 'Which device?'}), 400
    answer, error = _ask_agents('raw', name)
    if error:
        return error
    return jsonify({**answer['result'], 'agent': answer['name']})


@bp.route('/api/settings/telemetry/targets', methods=['POST'])
def add_target():
    return _save()


@bp.route('/api/settings/telemetry/targets/<target_id>', methods=['PUT'])
def change_target(target_id):
    return _save(target_id)


@bp.route('/api/settings/telemetry/targets/<target_id>', methods=['DELETE'])
def delete_target(target_id):
    gone = targets.delete(target_id)
    if gone is None:
        return jsonify({'error': 'That device is gone.'}), 404
    audit.record('telemetry', f"Removed telemetry from {gone['name']}", g.get('audit_user'))
    _tell_agents()
    return jsonify({'ok': True})


@bp.route('/api/settings/telemetry/targets/<target_id>/device-config', methods=['GET'])
def device_config(target_id):
    target = next((t for t in targets.raw_targets() if t['id'] == target_id), None)
    if target is None:
        return jsonify({'error': 'That device is gone.'}), 404
    collector = (request.args.get('collector') or '').strip()[:100] or '<collector address>'
    return jsonify({'config': telegraf.device_config(target, collector)})


@bp.route('/api/settings/telemetry/token', methods=['GET'])
def show_token():
    try:
        token = targets.ingest_token()
    except vault.VaultError as exc:
        return jsonify({'error': str(exc)}), 500
    audit.record('telemetry', 'Looked at the telemetry token', g.get('audit_user'))
    return jsonify({'token': token})


@bp.route('/api/settings/telemetry/token', methods=['POST'])
def renew_token():
    try:
        token = targets.new_ingest_token()
    except vault.VaultError as exc:
        return jsonify({'error': str(exc)}), 500
    audit.record('telemetry', 'Made a new telemetry token', g.get('audit_user'))
    return jsonify({'token': token})


@bp.route('/api/settings/telemetry/telegraf.conf', methods=['GET'])
def telegraf_conf():
    audit.record('telemetry', 'Downloaded the Telegraf configuration', g.get('audit_user'))
    return telemetry.render_here(), 200, {'Content-Type': 'text/plain; charset=utf-8',
                                          'Content-Disposition': 'attachment; filename="telegraf.conf"',
                                          'Cache-Control': 'no-store'}
