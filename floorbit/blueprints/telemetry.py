"""Device telemetry (docs/telemetry.md). Rules in floorbit/telemetry/.

For senders, with the ingest token (``Authorization: Token <token>``, the InfluxDB v2 way, or the
token as the password of Basic auth or ``?p=``, the InfluxDB v1 way), no account:

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
- ``GET /api/settings/telemetry/telegraf.conf``: Telegraf's config, secrets in it, for a
  Telegraf that doesn't run in the sidecar.

For the local agent, with its key (as blueprints/agent.py):

- ``GET /api/agent/v1/telemetry/config``: ``{"telegraf", "targets", "interval"}``. The agent writes
  the config for its Telegraf (with its own output address and token) and runs the API pollers.
- ``POST /api/agent/v1/telemetry`` ``{"at", "values": {series: value}, "lines": [...]}``: its
  normalised series, and (when this Floorbit has VictoriaMetrics) the points that came in, minus
  MAC tables and ARP.
"""
import base64
import time
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
    return request.args.get('p') or request.headers.get('Floorbit-Telemetry-Token')


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
    """What each configured device sent last, for the page."""
    out = {}
    with state_mod.state._lock:
        for dev in state_mod.state.devices.values():
            out[dev.name] = {'seen': dev.seen or None, 'online': dev.online(), 'ports': len(dev.interfaces),
                             'macs': len(dev.fdb), 'arp': len(dev.arp),
                             'neighbours': len(dev.lldp) + len(dev.cdp)}
    return out


@bp.route('/api/settings/telemetry', methods=['GET'])
def settings_view():
    return jsonify({'targets': targets.listing(), 'seen': _devices(), 'status': telemetry.status(),
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
    return jsonify(entry), 200 if target_id else 201


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


# ── the local agent ────────────────────────────────────────────────────────────────────────────

AGENT_TOKEN = '@@FLOORBIT_AGENT_INGEST_TOKEN@@'
AGENT_OUTPUT = '@@FLOORBIT_AGENT_INGEST_URL@@'


@bp.route('/api/agent/v1/telemetry/config', methods=['GET'])
def agent_config():
    from .agent import _agent, _refused
    agent = _agent()
    if agent is None:
        return _refused()
    raw = targets.raw_targets()
    opened = [targets.opened(t) for t in raw]
    # The agent puts in its own listener's address and token: they never leave the hall.
    conf = telegraf.render(opened, AGENT_OUTPUT, AGENT_TOKEN)
    version = _version(raw)
    if _sent.get(agent['id']) != version:
        # It carries the devices' secrets: say so once per change, not on every fetch.
        _sent[agent['id']] = version
        audit.record('telemetry', f"Sent the telemetry setup to the agent {agent['name']}", None, f'{len(raw)} devices')
    return jsonify({'telegraf': conf, 'token_placeholder': AGENT_TOKEN, 'output_placeholder': AGENT_OUTPUT,
                    'targets': opened, 'version': version})


_sent = {}


def _version(raw):
    """Changes when the devices do, so the agent only rewrites Telegraf's config then."""
    import hashlib
    import json
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()[:16]


@bp.route('/api/agent/v1/telemetry', methods=['POST'])
def agent_series():
    from .. import agent_link
    from ..telemetry import lineproto
    from .agent import _agent, _agent_body, _refused
    agent = _agent()
    if agent is None:
        return _refused()
    body = _agent_body()
    values = body.get('values') if isinstance(body.get('values'), dict) else {}
    clean = {}
    for key, value in list(values.items())[:200_000]:
        if isinstance(key, str) and key.count('|') == 2 and len(key) <= 300 and isinstance(value, (int, float)):
            clean[key] = float(value)
    at = body.get('at') if isinstance(body.get('at'), (int, float)) else time.time()
    # The hosted clock decides: an agent whose clock is off by more than a minute is not trusted.
    if abs(at - time.time()) > 60:
        at = time.time()
    store = storage.storage()
    if clean:
        store.sample(clean, at)
    lines = body.get('lines') if isinstance(body.get('lines'), list) else []
    if lines and storage.vm_url():
        points, _bad = lineproto.parse('\n'.join(str(x) for x in lines[:100_000]))
        store.forward_raw(points)
    agent_link.tunnel.relayed(agent['id'], 'telemetry', len(clean))
    return jsonify({'taken': len(clean), 'lines': bool(storage.vm_url())})

