"""Feature switches (issue #114). See docs/features.md.

An admin turns whole features off under Settings > Features. A feature that is off:

- leaves the navigation (``feature_on()`` in Jinja, ``useFeature()`` in React),
- answers 404 on its pages and API (``guard``, before sign-in is even checked),
- stops its background work (each watch loop asks ``on()`` before it polls).

``FLOORBIT_FEATURES_OFF=traffic,ports`` forces features off; the settings page can't turn those back on.
Kept in data.json under ``features`` as ``{id: false}``: only what was turned off, so a feature added
later starts on.

A new feature adds itself to ``FEATURES`` with the paths it owns.
"""
import os
import threading

from .store import load_data, save_data

KEY = 'features'
ENV = 'FLOORBIT_FEATURES_OFF'

# id, the paths it owns (a path and everything under it), and the features it needs.
FEATURES = (
    {'id': 'incidents', 'paths': ('/incidents', '/api/incidents'), 'needs': ()},
    {'id': 'helpdesk', 'paths': ('/help', '/api/helpdesk', '/incidents/qr', '/api/speedtests'),
     'needs': ('incidents',)},
    {'id': 'dispatch', 'paths': ('/jobs', '/api/jobs', '/api/dispatch'), 'needs': ('incidents',)},
    {'id': 'handover', 'paths': ('/handover', '/api/handover'), 'needs': ('incidents',)},
    {'id': 'gear', 'paths': ('/gear', '/api/gear'), 'needs': ()},
    {'id': 'cables', 'paths': ('/cables', '/api/cables', '/api/cables.csv'), 'needs': ()},
    {'id': 'health', 'paths': ('/health', '/api/health'), 'needs': ()},
    {'id': 'dashboard', 'paths': ('/dashboard', '/api/dashboard'), 'needs': ()},
    {'id': 'traffic', 'paths': ('/traffic', '/api/flows'), 'needs': ()},
    {'id': 'dns', 'paths': ('/dns', '/api/dns'), 'needs': ()},
    {'id': 'wifi', 'paths': ('/wifi', '/api/wifi'), 'needs': ()},
    {'id': 'games', 'paths': ('/games', '/api/games'), 'needs': ()},
    {'id': 'syslog', 'paths': ('/logs', '/api/logs'), 'needs': ()},
    {'id': 'forecast', 'paths': ('/api/forecast',), 'needs': ()},
    {'id': 'security', 'paths': ('/security', '/api/security'), 'needs': ()},
    {'id': 'ports', 'paths': ('/api/ports',), 'needs': ()},
    {'id': 'commands', 'paths': ('/commands', '/api/commands'), 'needs': ('ports',)},
    {'id': 'terminal', 'paths': ('/terminal', '/api/terminal'), 'needs': ('ports',)},
    {'id': 'power', 'paths': ('/power', '/api/power'), 'needs': ()},
    {'id': 'tournament', 'paths': ('/tournament', '/api/tournament'), 'needs': ()},
    {'id': 'replay', 'paths': ('/replay', '/api/replay'), 'needs': ()},
    {'id': 'timeline', 'paths': ('/timeline', '/api/timeline', '/api/timeline.csv'), 'needs': ()},
    {'id': 'report', 'paths': ('/report', '/api/report', '/api/report.pdf'), 'needs': ()},
    {'id': 'past_events', 'paths': ('/events', '/api/past-events'), 'needs': ('report',)},
    {'id': 'planner', 'paths': ('/planner', '/api/planner'), 'needs': ()},
    {'id': 'preflight', 'paths': ('/preflight', '/api/preflight', '/api/preflight.pdf'), 'needs': ()},
    {'id': 'teardown', 'paths': ('/teardown', '/api/teardown'), 'needs': ()},
    {'id': 'public_hall', 'paths': ('/hall', '/api/public'), 'needs': ()},
)
BY_ID = {f['id']: f for f in FEATURES}

_lock = threading.Lock()


class FeatureError(ValueError):
    pass


def forced_off():
    raw = os.environ.get(ENV) or ''
    return {p.strip().lower().replace('-', '_') for p in raw.split(',') if p.strip()} & set(BY_ID)


def _saved(data):
    raw = data.get(KEY)
    return {k: False for k, v in (raw or {}).items() if k in BY_ID and v is False} if isinstance(raw, dict) else {}


def off(data=None):
    """Every feature that is off: turned off, forced off, or needing one that is."""
    data = data if data is not None else load_data()
    result = set(_saved(data)) | forced_off()
    changed = True
    while changed:   # a feature is off when anything it needs is
        changed = False
        for f in FEATURES:
            if f['id'] not in result and any(n in result for n in f['needs']):
                result.add(f['id'])
                changed = True
    return result


def on(feature_id, data=None):
    return feature_id not in off(data)


def status(data=None):
    data = data if data is not None else load_data()
    saved, forced, now_off = _saved(data), forced_off(), off(data)
    return [{'id': f['id'], 'on': f['id'] not in now_off, 'chosen': f['id'] not in saved,
             'forced_off': f['id'] in forced, 'needs': list(f['needs'])} for f in FEATURES]


def update(changes):
    """Apply {id: bool}. Returns the ids that changed."""
    if not isinstance(changes, dict) or not changes:
        raise FeatureError('Send the features to change, like {"power": false}.')
    unknown = sorted(k for k in changes if k not in BY_ID)
    if unknown:
        raise FeatureError(f"Unknown feature(s): {', '.join(unknown)}")
    if any(not isinstance(v, bool) for v in changes.values()):
        raise FeatureError('Each feature is true (on) or false (off).')
    forced = sorted(k for k, v in changes.items() if v and k in forced_off())
    if forced:
        raise FeatureError(f"{', '.join(forced)} is turned off by {ENV} on the server.")
    with _lock:
        data = load_data()
        saved = _saved(data)
        changed = [k for k, v in changes.items() if (k not in saved) != v]
        for k, v in changes.items():
            if v:
                saved.pop(k, None)
            else:
                saved[k] = False
        data[KEY] = saved
        save_data(data)
    return changed


def owner(path):
    """The feature a request path belongs to, or None."""
    for f in FEATURES:
        if any(path == p or path.startswith(p + '/') for p in f['paths']):
            return f['id']
    return None


def guard(path):
    """True when the path belongs to a feature that is off."""
    feature = owner(path)
    return bool(feature) and feature in off()


def init_features(app):
    from flask import abort, jsonify, request

    def turned_off():
        if guard(request.path):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'This feature is turned off.'}), 404
            abort(404)
        return None

    # First, before sign-in: a feature that is off doesn't exist, for anybody.
    app.before_request_funcs.setdefault(None, []).insert(0, turned_off)

    @app.context_processor
    def features_for_templates():
        now_off = off()   # read once per page, not once per link
        return {'feature_on': lambda feature_id: feature_id not in now_off}
