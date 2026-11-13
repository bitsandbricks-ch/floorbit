"""Persisted application settings.

Settings are stored in data.json under the ``app_settings`` key. A value saved
from the settings page always wins; otherwise the environment variable is used,
and finally a built-in default. Secrets (API tokens) are write-only: the API
reports whether they are set and where they come from, never their value.
"""
import json
import os
import threading

import requests
from flask import Blueprint, jsonify, render_template, request

# ── Schema ─────────────────────────────────────────────────────────────────────

def _parse_bool(raw):
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in ('false', '0', 'no', 'off', '')


def _parse_list(raw):
    items = raw if isinstance(raw, list) else str(raw).split(',')
    return [str(i).strip() for i in items if str(i).strip()]


SECTIONS = [
    {'id': 'netbox',   'title': 'NetBox',
     'description': 'Source of the switch inventory. Leave the URL or token empty to place switches manually.'},
    {'id': 'librenms', 'title': 'LibreNMS',
     'description': 'Live switch status, port statistics and IP to switch-port resolution for seats.'},
    {'id': 'cache',    'title': 'Caching',
     'description': 'How long LibreNMS lookups are kept in Redis before they are fetched again.'},
    {'id': 'display',  'title': 'Display defaults',
     'description': 'Defaults for switches that have no per-device setting of their own.'},
]

# key, section, label, type, env var, default, help
FIELDS = [
    dict(key='netbox.url', section='netbox', label='URL', type='url',
         env='NETBOX_URL', default='', placeholder='https://netbox.example.com'),
    dict(key='netbox.token', section='netbox', label='API token', type='secret',
         env='NETBOX_TOKEN', default=''),
    dict(key='netbox.device_roles', section='netbox', label='Device roles', type='list',
         env='NETBOX_DEVICE_ROLE', default=['access-switch'],
         help='Comma-separated NetBox role slugs to import as switches.'),
    dict(key='netbox.verify_ssl', section='netbox', label='Verify TLS certificate', type='bool',
         env='NETBOX_VERIFY_SSL', default=True),

    dict(key='librenms.url', section='librenms', label='URL', type='url',
         env='LIBRENMS_URL', default='', placeholder='https://librenms.example.com'),
    dict(key='librenms.token', section='librenms', label='API token', type='secret',
         env='LIBRENMS_TOKEN', default=''),
    dict(key='librenms.verify_ssl', section='librenms', label='Verify TLS certificate', type='bool',
         env='LIBRENMS_VERIFY_SSL', default=True),
    dict(key='librenms.fdb_exclude', section='librenms', label='Ignored port names', type='list',
         env='LIBRENMS_FDB_EXCLUDE',
         default=['port-channel', 'vlan', 'virtual', 'tunnel', 'loopback', 'po'],
         help='When locating a MAC address, ports whose name contains any of these are skipped (uplinks, LAGs, SVIs).'),

    dict(key='cache.ttl_arp', section='cache', label='ARP table TTL', type='int', unit='seconds',
         env='CACHE_TTL_ARP', default=300, min=1, max=86400),
    dict(key='cache.ttl_mac', section='cache', label='MAC table TTL', type='int', unit='seconds',
         env='CACHE_TTL_MAC', default=300, min=1, max=86400),
    dict(key='cache.ttl_resolve', section='cache', label='Seat resolution TTL', type='int', unit='seconds',
         env='CACHE_TTL_RESOLVE', default=30, min=1, max=86400,
         help='How long an IP to switch-port result is reused.'),

    dict(key='display.hide_labels', section='display', label='Hide switch labels', type='bool',
         env=None, default=False),
    dict(key='display.exclude_heatmap', section='display', label='Exclude switches from heatmap', type='bool',
         env=None, default=False),
]
FIELDS_BY_KEY = {f['key']: f for f in FIELDS}


class SettingsError(ValueError):
    pass


def _coerce(field, raw):
    """Turn a stored/env/request value into the field's type, or raise SettingsError."""
    t = field['type']
    if t == 'bool':
        return _parse_bool(raw)
    if t == 'list':
        return _parse_list(raw)
    if t == 'int':
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise SettingsError(f"{field['label']} must be a whole number") from None
        lo, hi = field.get('min'), field.get('max')
        if (lo is not None and val < lo) or (hi is not None and val > hi):
            raise SettingsError(f"{field['label']} must be between {lo} and {hi}")
        return val
    val = '' if raw is None else str(raw).strip()
    if t == 'url':
        val = val.rstrip('/')
        if val and not (val.startswith('http://') or val.startswith('https://')):
            raise SettingsError(f"{field['label']} must start with http:// or https://")
    return val


# ── Store ──────────────────────────────────────────────────────────────────────

class SettingsStore:
    def __init__(self, data_file, environ=None):
        self.data_file = data_file
        self.environ = os.environ if environ is None else environ
        self._lock = threading.Lock()
        self._overrides = {}
        self._mtime = None
        self.reload()

    # file IO -------------------------------------------------------------
    def _read_file(self, strict=False):
        if not os.path.exists(self.data_file):
            return {}
        try:
            with open(self.data_file) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            if strict:
                # Never overwrite a data file we could not parse.
                raise OSError(f'{self.data_file} is unreadable or not valid JSON') from exc
            return {}

    def _current_mtime(self):
        try:
            return os.path.getmtime(self.data_file)
        except OSError:
            return None

    @staticmethod
    def _overrides_from(data):
        overrides = dict(data.get('app_settings') or {})
        # Migrate the old /api/settings shape ({hide_labels, exclude_heatmap}).
        legacy = data.get('default_settings') or {}
        for old, new in (('hide_labels', 'display.hide_labels'),
                         ('exclude_heatmap', 'display.exclude_heatmap')):
            if old in legacy and new not in overrides:
                overrides[new] = bool(legacy[old])
        return {k: v for k, v in overrides.items() if k in FIELDS_BY_KEY}

    def reload(self):
        self._overrides = self._overrides_from(self._read_file())
        self._mtime = self._current_mtime()

    def reload_if_changed(self):
        """Re-read the file if it changed on disk. Returns True when it did."""
        if self._current_mtime() != self._mtime:
            self.reload()
            return True
        return False

    # reads ---------------------------------------------------------------
    def source(self, key):
        field = FIELDS_BY_KEY[key]
        if key in self._overrides:
            return 'saved'
        if field.get('env') and self.environ.get(field['env'], '') != '':
            return 'env'
        return 'default'

    def get(self, key):
        field = FIELDS_BY_KEY[key]
        src = self.source(key)
        try:
            if src == 'saved':
                return _coerce(field, self._overrides[key])
            if src == 'env':
                return _coerce(field, self.environ[field['env']])
        except SettingsError:
            pass   # a bad env/stored value falls back to the default
        default = field['default']
        return list(default) if isinstance(default, list) else default

    def public_values(self):
        """All values for the API. Secrets are reported as set/unset only."""
        out = {}
        for f in FIELDS:
            key = f['key']
            entry = {'source': self.source(key)}
            if f['type'] == 'secret':
                entry['is_set'] = bool(self.get(key))
            else:
                entry['value'] = self.get(key)
            if f.get('env'):
                entry['env'] = f['env']
                entry['env_set'] = self.environ.get(f['env'], '') != ''
            out[key] = entry
        return out

    # writes --------------------------------------------------------------
    def update(self, changes):
        """Apply {key: value}. None resets a key to env/default.

        For secrets an empty string or missing key keeps the current value;
        use None to drop the saved token.
        """
        if not isinstance(changes, dict):
            raise SettingsError('Expected a JSON object')
        unknown = [k for k in changes if k not in FIELDS_BY_KEY]
        if unknown:
            raise SettingsError(f"Unknown setting(s): {', '.join(sorted(unknown))}")

        staged = {}
        for key, raw in changes.items():
            field = FIELDS_BY_KEY[key]
            if raw is None:
                staged[key] = None
                continue
            if field['type'] == 'secret' and str(raw).strip() == '':
                continue
            staged[key] = _coerce(field, raw)

        with self._lock:
            data = self._read_file(strict=True)
            stored = self._overrides_from(data)
            for key, val in staged.items():
                if val is None:
                    stored.pop(key, None)
                else:
                    stored[key] = val
            data['app_settings'] = stored
            data.pop('default_settings', None)   # migrated into app_settings
            # Write in place: data.json is bind-mounted in docker-compose, so an
            # atomic rename onto it would fail.
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.reload()


# ── Connection tests ───────────────────────────────────────────────────────────

def _test_http(url, headers, verify, ok_message):
    try:
        resp = requests.get(url, headers=headers, timeout=8, verify=verify)
    except requests.exceptions.SSLError as exc:
        return {'ok': False, 'message': (
            f'TLS error: {exc.__class__.__name__}. '
            'Turn off certificate verification if the server uses a self-signed certificate.'
        )}
    except requests.RequestException as exc:
        return {'ok': False, 'message': f'Could not connect: {exc.__class__.__name__}'}
    if resp.status_code in (401, 403):
        return {'ok': False, 'message': f'Connected, but the token was rejected (HTTP {resp.status_code}).'}
    if not resp.ok:
        return {'ok': False, 'message': f'Server answered HTTP {resp.status_code}.'}
    try:
        payload = resp.json()
    except ValueError:
        return {'ok': False, 'message': 'Server answered, but not with JSON. Check the URL.'}
    return {'ok': True, 'message': ok_message(payload)}


def test_netbox(url, token, verify):
    if not url or not token:
        return {'ok': False, 'message': 'URL and token are required.'}
    return _test_http(
        f'{url}/api/status/',
        {'Authorization': f'Token {token}', 'Accept': 'application/json'},
        verify,
        lambda p: f"Connected to NetBox {p.get('netbox-version', '')}".strip(),
    )


def test_librenms(url, token, verify):
    if not url or not token:
        return {'ok': False, 'message': 'URL and token are required.'}

    def msg(p):
        sysinfo = (p.get('system') or [{}])[0] if isinstance(p.get('system'), list) else {}
        version = sysinfo.get('local_ver') or ''
        return f'Connected to LibreNMS {version}'.strip()

    return _test_http(
        f'{url}/api/v0/system',
        {'X-Auth-Token': token, 'Accept': 'application/json'},
        verify,
        msg,
    )


# ── Blueprint ──────────────────────────────────────────────────────────────────

def create_settings_blueprint(store, on_change, get_redis=None, redis_info=None):
    """Routes for the settings page and its API.

    on_change() is called after a successful save so the app can re-read its
    runtime configuration. get_redis() returns a client or None.
    """
    bp = Blueprint('settings', __name__)

    def payload():
        return {
            'sections': SECTIONS,
            'fields': FIELDS,
            'values': store.public_values(),
            'status': {
                'netbox_enabled':   bool(store.get('netbox.url') and store.get('netbox.token')),
                'librenms_enabled': bool(store.get('librenms.url') and store.get('librenms.token')),
                'redis':            redis_info() if redis_info else None,
            },
        }

    @bp.route('/settings')
    def settings_page():
        return render_template('settings.html')

    @bp.route('/api/settings', methods=['GET'])
    def get_settings():
        store.reload_if_changed()
        return jsonify(payload())

    @bp.route('/api/settings', methods=['PUT', 'PATCH'])
    def update_settings():
        body = request.get_json(silent=True)
        try:
            store.update(body)
        except SettingsError as exc:
            return jsonify({'error': str(exc)}), 400
        except OSError as exc:
            return jsonify({'error': f'Could not save settings: {exc}'}), 500
        on_change()
        return jsonify(payload())

    @bp.route('/api/settings/test/<service>', methods=['POST'])
    def test_connection(service):
        """Test a connection using the form's unsaved values, falling back to saved ones."""
        body = request.get_json(silent=True) or {}

        def pick(key):
            if key in body and body[key] not in (None, ''):
                try:
                    return _coerce(FIELDS_BY_KEY[key], body[key])
                except SettingsError:
                    return None
            return store.get(key)

        if service == 'netbox':
            return jsonify(test_netbox(pick('netbox.url'), pick('netbox.token'), pick('netbox.verify_ssl')))
        if service == 'librenms':
            return jsonify(test_librenms(pick('librenms.url'), pick('librenms.token'), pick('librenms.verify_ssl')))
        if service == 'redis':
            client = get_redis() if get_redis else None
            if not client:
                return jsonify({'ok': False, 'message': 'Not connected to Redis. Caching is disabled.'})
            try:
                client.ping()
                return jsonify({'ok': True, 'message': f'Connected, {client.dbsize()} keys cached.'})
            except Exception as exc:  # noqa: BLE001  # redis raises several unrelated types
                return jsonify({'ok': False, 'message': f'Redis error: {exc.__class__.__name__}'})
        return jsonify({'error': f'Unknown service: {service}'}), 404

    return bp
