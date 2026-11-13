"""Optional integrations for the floor plan app.

Wire-up from app.py is one call::

    from integrations import init_integrations
    init_integrations(app, load_data=load_data,
                      settings_store=globals().get('settings_store'))

When a settings store is passed, the integration settings show up on the
/settings page and saved values win over env vars (see settings_bridge.py).

What it adds:

* ``GET  /api/events``                 live push stream (Server-Sent Events)
* ``GET  /api/integrations``           status of every integration + settings schema
* ``GET  /api/status/snapshot``        last known status per switch from the monitor
* ``POST /api/integrations/discord/test``  send a test message to the webhook
* ``POST /api/integrations/monitor/poll``  run one status poll now
* ``GET  /api/seats/sources``          seat mapping sources and their errors
* ``GET  /checkin`` + ``POST /api/checkin``  seat check-in page (CHECKIN_ENABLED)
* ``GET  /api/checkin/me``             the check-in for the caller's IP
* ``GET  /api/checkins``, ``DELETE /api/checkins/<seat>``  user/IP/seat/MAC table
* ``GET  /checkins/history``           who sat where over time, with filters
* ``GET  /api/checkins/history[.csv]`` the same as JSON or a CSV download
* a ``data.changed`` event after every successful write to switches / seat blocks
* a background status monitor and Discord alerts (when configured)

All settings are read through ``integrations.config`` (env vars today, the
settings page later).
"""
import hmac
import threading
import time

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from . import checkin, config, events, history, seat_sources, settings_bridge
from .discord import DiscordNotifier
from .monitor import StatusMonitor

__all__ = ['init_integrations', 'config', 'events', 'seat_sources', 'checkin', 'history']

# Writes under these prefixes are announced to other browsers
_WATCHED_PREFIXES = {
    '/api/switches': 'switches',
    '/api/seat-blocks': 'seat-blocks',
    '/api/settings': 'settings',
}


def _placed_switches(load_data):
    def list_switches():
        data = load_data()
        out = []
        for s in data.get('switches', []):
            if s.get('placed', True) and s.get('name'):
                out.append({'id': s['id'], 'name': s['name'], 'source': 'manual'})
        positions = data.get('positions', {}) or {}
        for d in data.get('cached_devices', []):
            if d['id'] in positions and positions[d['id']]:
                out.append({'id': d['id'], 'name': d['name'], 'source': 'netbox'})
        return out
    return list_switches


def init_integrations(app, load_data, settings_store=None, start_background=True):
    if settings_store is not None:
        settings_bridge.connect(settings_store)
    monitor = StatusMonitor(_placed_switches(load_data))
    refresher = checkin.CheckinRefresher()
    discord = DiscordNotifier()
    discord.attach()

    bp = Blueprint('integrations', __name__)

    @bp.route('/api/events')
    def event_stream():
        if not config.get_bool('LIVE_UPDATES_ENABLED', True):
            return jsonify({'error': 'Live updates are disabled'}), 404
        hello = {'statuses': monitor.snapshot(), 'monitor': monitor.enabled()}
        resp = Response(stream_with_context(events.stream(hello)), mimetype='text/event-stream')
        resp.headers['Cache-Control'] = 'no-cache'
        resp.headers['X-Accel-Buffering'] = 'no'   # nginx: don't buffer the stream
        return resp

    @bp.route('/api/integrations')
    def integrations_status():
        return jsonify({
            'live': {'enabled': config.get_bool('LIVE_UPDATES_ENABLED', True),
                     'clients': events.client_count()},
            'monitor': monitor.info(),
            'discord': discord.info(),
            'seat_sources': seat_sources.info(),
            'checkin': {'enabled': config.get_bool('CHECKIN_ENABLED', False),
                        'count': len(checkin.load_all()),
                        'history': history.enabled(),
                        'last_refresh': refresher.last_run,
                        'last_error': refresher.last_error},
            'settings': config.describe(),
        })

    @bp.route('/api/status/snapshot')
    def status_snapshot():
        return jsonify({'statuses': monitor.snapshot(), 'counts': monitor.counts(),
                        'last_poll': monitor.last_poll})

    @bp.route('/api/integrations/discord/test', methods=['POST'])
    def discord_test():
        if not discord.webhook():
            return jsonify({'ok': False, 'error': 'DISCORD_WEBHOOK_URL is not set'}), 400
        try:
            discord.send(discord.build_test_message())
        except Exception as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 502
        return jsonify({'ok': True})

    @bp.route('/api/integrations/monitor/poll', methods=['POST'])
    def monitor_poll():
        if not monitor.enabled():
            return jsonify({'ok': False, 'error': 'Status monitor is disabled or LibreNMS is not configured'}), 400
        try:
            changes = monitor.poll_once()
        except Exception as exc:
            monitor.last_error = str(exc)
            return jsonify({'ok': False, 'error': str(exc)}), 502
        return jsonify({'ok': True, 'changes': changes, 'counts': monitor.counts()})

    @bp.route('/api/seats/sources')
    def seat_sources_info():
        if request.args.get('refresh'):
            seat_sources.invalidate()
            seat_sources.load()
        return jsonify(seat_sources.info())

    # ── Seat check-in ───────────────────────────────────────────────────────
    def checkin_disabled():
        if not config.get_bool('CHECKIN_ENABLED', False):
            return jsonify({'error': 'Check-in is disabled'}), 404
        return None

    def admin_denied():
        token = config.get('CHECKIN_ADMIN_TOKEN', '') or ''
        given = request.headers.get('X-Admin-Token') or request.args.get('token') or ''
        if token and not hmac.compare_digest(token, given):
            return jsonify({'error': 'Admin token required'}), 401
        return None

    @bp.route('/checkin')
    def checkin_page():
        if not config.get_bool('CHECKIN_ENABLED', False):
            return 'Check-in is not open.', 404
        return render_template('checkin.html')

    @bp.route('/api/checkin', methods=['POST'])
    def checkin_submit():
        denied = checkin_disabled()
        if denied:
            return denied
        body = request.get_json(silent=True) or request.form
        try:
            row = checkin.check_in(body.get('seat'), body.get('username'), checkin.client_ip(),
                                   load_data, user_agent=request.headers.get('User-Agent'))
        except checkin.CheckinError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), exc.status
        return jsonify({'ok': True, 'seat': row['seat'], 'username': row['username'],
                        'ip': row['ip'], 'mac_found': bool(row['mac'])})

    @bp.route('/api/checkin/me')
    def checkin_me():
        denied = checkin_disabled()
        if denied:
            return denied
        ip = checkin.client_ip()
        row = checkin.find_by_ip(ip)
        return jsonify({'ip': ip, 'checkin': (
            {'seat': row['seat'], 'username': row['username']} if row else None)})

    @bp.route('/api/checkins')
    def checkin_list():
        denied = checkin_disabled() or admin_denied()
        if denied:
            return denied
        rows = sorted(checkin.load_all().values(), key=lambda r: r['seat'])
        return jsonify({'checkins': rows, 'refresh': {
            'last_run': refresher.last_run, 'last_error': refresher.last_error}})

    @bp.route('/api/checkins/<seat>', methods=['DELETE'])
    def checkin_delete(seat):
        denied = checkin_disabled() or admin_denied()
        if denied:
            return denied
        if not checkin.remove(seat):
            return jsonify({'error': 'No check-in for that seat'}), 404
        return jsonify({'ok': True})

    @bp.route('/api/checkins/refresh', methods=['POST'])
    def checkin_refresh():
        denied = checkin_disabled() or admin_denied()
        if denied:
            return denied
        return jsonify({'ok': True, 'changed': checkin.refresh_once()})

    # ── Check-in history ────────────────────────────────────────────────────
    # Not tied to CHECKIN_ENABLED: the log stays readable after check-in is
    # closed, which is when it gets exported. The admin token still applies.
    def history_rows():
        view = request.args.get('view', 'sessions')
        if view not in ('events', 'sessions'):
            raise ValueError('view must be "sessions" or "events".')
        return view, history.query(request.args, view)

    @bp.route('/checkins/history')
    def history_page():
        return render_template('checkin_history.html')

    @bp.route('/api/checkins/history')
    def history_list():
        denied = admin_denied()
        if denied:
            return denied
        try:
            view, rows = history_rows()
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        limit = max(1, min(request.args.get('limit', 500, type=int), 5000))
        return jsonify({'view': view, 'total': len(rows), 'enabled': history.enabled(),
                        'rows': history.to_json_rows(rows[:limit], view)})

    @bp.route('/api/checkins/history.csv')
    def history_csv():
        denied = admin_denied()
        if denied:
            return denied
        try:
            view, rows = history_rows()
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        filename = f"lal-checkins-{view}-{time.strftime('%Y%m%d-%H%M')}.csv"
        return Response(history.to_csv(rows, view), mimetype='text/csv',
                        headers={'Content-Disposition': f'attachment; filename="{filename}"',
                                 'Cache-Control': 'no-store'})

    app.register_blueprint(bp)

    @app.after_request
    def announce_changes(response):
        if request.method in ('POST', 'PUT', 'DELETE') and response.status_code < 400:
            for prefix, resource in _WATCHED_PREFIXES.items():
                if request.path.startswith(prefix):
                    events.publish('data.changed', {
                        'resource': resource,
                        'method': request.method,
                        'path': request.path,
                    }, origin=request.headers.get('X-Client-Id'))
                    break
        return response

    # Start the monitor on the first request, not at import: with Flask's
    # debug reloader the module is imported twice, but only the serving
    # process gets requests.
    started = threading.Event()

    @app.before_request
    def start_monitor_once():
        if start_background and not started.is_set():
            started.set()
            monitor.start()
            refresher.start()

    app.extensions['lal_integrations'] = {'monitor': monitor, 'discord': discord,
                                          'checkin_refresher': refresher}
    return app.extensions['lal_integrations']
