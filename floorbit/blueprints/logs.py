"""Logs (issue #91): what switches, firewalls and DHCP servers sent by syslog. Receiving and keeping
lives in floorbit/syslog.py.

- ``GET /logs``: the page.
- ``GET /api/logs``: newest lines first, with the receiver's status. Filters: ``q`` (words that all
  have to be in the line), ``device``, ``seat``, ``port`` (``Gi1/0/4`` or ``GigabitEthernet1/0/4``),
  ``severity`` (the least severe level to show, ``warning`` shows emerg to warning), ``after`` (only
  lines newer than this id, for the live tail), ``before`` (only older, for paging) and ``limit``
  (1 to 1000, 200 by default). Needs ``seats.view``: logs name MACs and IPs. ``source=app`` reads
  Floorbit's own log and ``source=audit`` the audit log instead, with the same filters (issue #93);
  both also need ``audit.read``. ``source=plugin:loki`` searches what a logs plugin keeps, with
  ``q`` in its query language (LogQL) over the last ``hours`` (24). For the syslog, ``since`` and
  ``until`` (unix seconds) keep only lines of that time.
- ``GET /api/logs/volume``: the syslog's lines per time slice (``buckets``, 60 by default) from ``since``
  (an hour ago by default) to ``until`` (now), with the same filters: ``[start, lines, errors]`` per slice,
  for the chart over the list (issue #1048).
- ``GET /api/logs/download``: every syslog line the filters match, oldest first, as a text file.
  The download is written to the audit log: the lines name MACs and IPs.
- ``GET /api/logs/markers``: warnings and worse of the last 10 minutes, counted per seat and per
  switch, for the floor plan (issue #92).
- ``GET /api/logs/alerts``: lines that matched a known pattern (err-disable, DHCP snooping, port
  security, MAC flapping, loops, storms, spanning tree), one item per pattern, device and port.
"""
from flask import Blueprint, current_app, jsonify, request

from .. import inventory, spa, syslog
from ..store import load_data

bp = Blueprint('logs', __name__)


@bp.app_context_processor
def syslog_flags():
    receiver = current_app.extensions.get('floorbit_syslog')
    on = bool(receiver and (syslog.settings()['enabled'] or receiver.demo))
    # The page also shows Floorbit's own log and the audit log, for those who may read them.
    return {'syslog_on': on, 'logs_page': on or _can('audit.read')}


@bp.route('/logs')
def logs_page():
    return spa.render('Logs')


def _int(name, default, low, high):
    raw = request.args.get(name)
    if raw in (None, ''):
        return default
    value = int(raw)   # ValueError is answered below
    if not low <= value <= high:
        raise ValueError
    return value


SOURCES = ('syslog', 'app', 'audit')


def _can(permission):
    from auth import current_user, roles  # late: auth imports floorbit while it loads
    if not current_app.extensions['auth'].enabled:
        return True
    user = current_user()
    return bool(user and roles.can(user, permission))


def sources():
    """The logs this account may read: the syslog with seats.view (the API's own rule) and what
    logs plugins (Loki) keep of it, Floorbit's own log and the audit log with audit.read."""
    stores = [f'plugin:{s.id}' for s in current_app.extensions['floorbit_syslog'].log_plugins()]
    return ['syslog', *stores] + (['app', 'audit'] if _can('audit.read') else [])


def _from_store(source, args, before, limit, status):
    """Search a logs plugin with its own query language (LogQL for Loki), newest first."""
    import time

    from ..plugins import PluginError
    try:
        hours = int(args.get('hours') or 24)
    except ValueError:
        hours = 0
    if not 1 <= hours <= 24 * 90:
        return jsonify({'error': 'hours is a whole number from 1 to 2160.'}), 400
    end = before / 1e6 if before else time.time()   # a plugin line's id is its time in microseconds
    query = (args.get('q') or '').strip()   # empty: the plugin's own "everything Floorbit sent"
    try:
        lines = current_app.extensions['floorbit_syslog'].query(source[len('plugin:'):], query, end - hours * 3600,
                                                                end, limit)
    except PluginError as exc:
        return jsonify({'lines': [], 'status': {**status, 'query_error': str(exc)}})
    return jsonify({'lines': lines or [], 'status': {**status, 'query': query}})


@bp.route('/api/logs', methods=['GET'])
def get_logs():
    args = request.args
    try:
        after = _int('after', 0, 0, 2**53)
        before = _int('before', None, 1, 2**53)
        limit = _int('limit', 200, 1, 1000)
    except ValueError:
        return jsonify({'error': 'after and before are line ids; limit is a whole number from 1 to 1000.'}), 400
    severity = (args.get('severity') or '').strip().lower()
    if severity and severity not in syslog.SEVERITIES:
        return jsonify({'error': f"severity is one of {', '.join(syslog.SEVERITIES)}."}), 400
    source = (args.get('source') or 'syslog').strip()
    allowed = sources()
    if source not in SOURCES and not source.startswith('plugin:'):
        return jsonify({'error': f"source is one of {', '.join(SOURCES)} or plugin:<id>."}), 400
    if source.startswith('plugin:') and source not in allowed:
        return jsonify({'error': 'That logs plugin is not turned on.'}), 404
    if source not in allowed:
        return jsonify({'error': 'Reading this log needs the audit.read permission.'}), 403
    receiver = current_app.extensions['floorbit_syslog']
    status = {**receiver.status(), 'sources': allowed, 'source': source}
    if source.startswith('plugin:'):
        return _from_store(source, args, before, limit, status)
    if source == 'app':
        lines = current_app.extensions['floorbit_app_log'].search(
            q=args.get('q', ''), device=args.get('device', ''), severity=severity, before=before, limit=limit)
        return jsonify({'lines': lines, 'status': status})
    if source == 'audit':
        from .. import audit
        lines = audit.as_log_lines(q=args.get('q', ''), severity=severity, before=before, limit=limit)
        device = (args.get('device') or '').lower()
        return jsonify({'lines': [ln for ln in lines if not device or ln['device'].lower() == device],
                        'status': status})
    try:
        since, until = _window()
    except ValueError:
        return jsonify({'error': WINDOW_ERROR}), 400
    lines = receiver.search(**_filters(severity), after=after, before=before, limit=limit, since=since, until=until)
    return jsonify({'lines': lines, 'status': status})


WINDOW_ERROR = 'since and until are unix seconds, since before until.'


def _window(default_since=None, default_until=None):
    def read(name, default):
        raw = request.args.get(name)
        if raw in (None, ''):
            return default
        value = float(raw)   # ValueError is answered by the caller
        if not 0 <= value < 2**33:
            raise ValueError
        return value
    since, until = read('since', default_since), read('until', default_until)
    if since is not None and until is not None and since >= until:
        raise ValueError
    return since, until


def _filters(severity):
    args = request.args
    return {'q': args.get('q', ''), 'device': args.get('device', ''), 'seat': args.get('seat', ''),
            'port': args.get('port', ''), 'severity': severity}


def _severity():
    severity = (request.args.get('severity') or '').strip().lower()
    if severity and severity not in syslog.SEVERITIES:
        raise ValueError(f"severity is one of {', '.join(syslog.SEVERITIES)}.")
    return severity


@bp.route('/api/logs/volume', methods=['GET'])
def get_volume():
    import time
    now = time.time()
    try:
        severity = _severity()
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    try:
        since, until = _window(now - 3600, now)
        buckets = _int('buckets', 60, 1, 500)
    except ValueError:
        return jsonify({'error': WINDOW_ERROR + ' buckets is a whole number from 1 to 500.'}), 400
    return jsonify(current_app.extensions['floorbit_syslog'].volume(
        since, until, buckets, **_filters(severity)))


DOWNLOAD_LIMIT = 200_000


@bp.route('/api/logs/download', methods=['GET'])
def download():
    import time

    from flask import Response, g

    from .. import audit
    try:
        severity = _severity()
        since, until = _window()
    except ValueError as exc:
        return jsonify({'error': str(exc) if str(exc).startswith('severity') else WINDOW_ERROR}), 400
    lines = current_app.extensions['floorbit_syslog'].search(**_filters(severity), limit=DOWNLOAD_LIMIT,
                                                             since=since, until=until)
    audit.record('security', 'Downloaded syslog lines', g.get('audit_user'), f'{len(lines)} lines')

    def row(line):
        at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(line.get('ts') or 0))
        where = ' '.join(str(line.get(k)) for k in ('device', 'port', 'seat') if line.get(k))
        program = f"{line['program']}: " if line.get('program') else ''
        return f"{at} {line['severity']:<7} {where} {program}{line['message']}\n"
    name = time.strftime('floorbit-syslog-%Y%m%d-%H%M.log', time.gmtime())
    return Response(''.join(row(ln) for ln in reversed(lines)), mimetype='text/plain',
                    headers={'Content-Disposition': f'attachment; filename="{name}"'})


@bp.route('/api/logs/markers', methods=['GET'])
def get_markers():
    devices = {d['name'].lower(): d['id'] for d in inventory.devices(load_data())}
    return jsonify(current_app.extensions['floorbit_syslog'].markers(devices))


@bp.route('/api/logs/alerts', methods=['GET'])
def get_alerts():
    return jsonify({'alerts': current_app.extensions['floorbit_syslog'].alert_items()})
