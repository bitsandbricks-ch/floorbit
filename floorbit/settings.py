"""Persisted application settings.

Settings are stored in data.json under the ``app_settings`` key. A value saved
from the settings page always wins; otherwise the environment variable is used,
and finally a built-in default. Secrets (API tokens) are write-only: the API
reports whether they are set and where they come from, never their value.
"""
import base64
import binascii
import json
import os
import re
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
    {'id': 'signin', 'title': 'Discord sign-in',
     'description': 'A "Sign in with Discord" button on the sign-in page. Create an application at '
                    'discord.com/developers, add <this site>/auth/discord/callback as an OAuth2 redirect '
                    '(set Public URL under General when the app runs behind a proxy) and paste its client '
                    'ID and secret here. Without a server, only accounts linked on the Users page can use it.'},
    {'id': 'public', 'title': 'Attendee pages',
     'description': 'Pages for attendees, open without an account. They show seat numbers only: '
                    'no nicks, addresses, switches or ports.'},
    {'id': 'appearance', 'title': 'Appearance',
     'description': 'The look of every page. A screen can pick its own preset with ?theme= '
                    '(for example /kiosk?theme=kiosk); ?theme=default goes back to this one.'},
]

THEME_PRESETS = [
    {'value': 'floorbit', 'label': 'Floorbit'},
    {'value': 'ops',      'label': 'Ops desk (dense, cyan accent)'},
    {'value': 'kiosk',    'label': 'Kiosk (big screen, dark)'},
    {'value': 'classic',  'label': 'Classic (the old orange look, dark)'},
    {'value': 'custom',   'label': 'Custom (your event colours below)'},
]
LOGO_MAX_BYTES = 256 * 1024
LOGO_TYPES = ('image/svg+xml', 'image/png', 'image/jpeg', 'image/webp')

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

    dict(key='signin.discord_client_id', section='signin', label='Client ID', type='text',
         env='DISCORD_CLIENT_ID', default='', placeholder='123456789012345678'),
    dict(key='signin.discord_client_secret', section='signin', label='Client secret', type='secret',
         env='DISCORD_CLIENT_SECRET', default=''),
    dict(key='signin.discord_guild_id', section='signin', label='Server ID', type='text',
         env='DISCORD_GUILD_ID', default='', placeholder='Empty: linked accounts only',
         help='Members of this Discord server can sign in, and get an account on their first sign-in. '
              'Right-click the server in Discord (developer mode on) and copy its ID.'),
    dict(key='signin.discord_admin_roles', section='signin', label='Admin roles', type='list',
         env='DISCORD_ADMIN_ROLES', default=[],
         help='Comma-separated Discord role IDs whose members become admins.'),
    dict(key='signin.discord_editor_roles', section='signin', label='Editor roles', type='list',
         env='DISCORD_EDITOR_ROLES', default=[],
         help='Role IDs whose members become editors.'),
    dict(key='signin.discord_viewer_roles', section='signin', label='Viewer roles', type='list',
         env='DISCORD_VIEWER_ROLES', default=[],
         help='Role IDs whose members become viewers. With all three role lists empty, every '
              'member of the server can sign in as a viewer; otherwise members without one of '
              'these roles are refused. The role is set on the first sign-in; change it on the Users page later.'),

    dict(key='public.attendee_view', section='public', label='Attendee view', type='bool',
         env='ATTENDEE_VIEW', default=False,
         help='/hall shows the hall plan with every seat online or offline. Off by default because '
              'it also shows when a seat is empty, for example while its player is away.'),
    dict(key='public.status_page', section='public', label='Network status page', type='bool',
         env='STATUS_PAGE', default=False,
         help='/status tells attendees whether the network is fine, which areas an outage hits, and the '
              "crew's updates. Off by default."),
    dict(key='public.status_switch_names', section='public', label='Switch names on the status page', type='bool',
         env='STATUS_SWITCH_NAMES', default=False,
         help='Name the switches that are down on /status. Off: only halls, blocks and rows.'),

    dict(key='theme.preset', section='appearance', label='Theme', type='choice',
         options=THEME_PRESETS, env='FLOORBIT_THEME', default='floorbit'),
    dict(key='theme.name', section='appearance', label='Event name', type='text',
         env='FLOORBIT_EVENT_NAME', default='', placeholder='LAN Party 2026',
         help='Shown in the top bar and as the kiosk heading. Empty shows the Floorbit logo.'),
    dict(key='theme.logo', section='appearance', label='Event logo', type='image',
         env=None, default='',
         help='SVG, PNG, JPEG or WebP up to 256 KB. Replaces the Floorbit logo in the top bar; '
              'the powered-by footer stays.'),
    dict(key='theme.accent', section='appearance', label='Accent colour', type='color',
         env=None, default='', theme='custom',
         help='Buttons, links and focus. Status colours (up, down, warning) never change.'),
    dict(key='theme.background', section='appearance', label='Background', type='color',
         env=None, default='', theme='custom',
         help='A dark background gives a dark-only theme, a light one a light-only theme.'),
    dict(key='theme.surface', section='appearance', label='Panels', type='color',
         env=None, default='', theme='custom', help='Empty: a shade of the background.'),
    dict(key='theme.text', section='appearance', label='Text', type='color',
         env=None, default='', theme='custom', help='Empty: near white or near black, by background.'),
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
    if t == 'choice':
        options = [o['value'] for o in field['options']]
        if val not in options:
            raise SettingsError(f"{field['label']} must be one of: {', '.join(options)}")
    if t == 'color':
        val = val.lower()
        if val and not re.fullmatch(r'#[0-9a-f]{6}', val):
            raise SettingsError(f"{field['label']} must be a colour like #2ee59d")
    if t == 'image' and val:
        _check_image(field, val)
    if t == 'url':
        val = val.rstrip('/')
        if val and not (val.startswith('http://') or val.startswith('https://')):
            raise SettingsError(f"{field['label']} must start with http:// or https://")
    return val


def _check_image(field, data_url):
    """A logo is stored inline as a data: URL, so backups carry it and offline LANs need no host."""
    m = re.fullmatch(r'data:([\w/+.-]+);base64,([A-Za-z0-9+/=\s]+)', data_url)
    if not m or m.group(1) not in LOGO_TYPES:
        raise SettingsError(f"{field['label']} must be an SVG, PNG, JPEG or WebP image")
    try:
        size = len(base64.b64decode(m.group(2), validate=False))
    except (binascii.Error, ValueError):
        raise SettingsError(f"{field['label']} is not a valid image") from None
    if size > LOGO_MAX_BYTES:
        raise SettingsError(f"{field['label']} must be {LOGO_MAX_BYTES // 1024} KB or smaller")


def check_changes(changes):
    """Validate {key: value} the way a save does, without saving. Returns the coerced values."""
    out = {}
    for key, raw in changes.items():
        field = FIELDS_BY_KEY.get(key)
        if field is None:
            raise SettingsError(f'Unknown setting: {key}')
        out[key] = None if raw is None else _coerce(field, raw)
    return out


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
            from .store import read_json
            return read_json(self.data_file, {})
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
            from .store import write_json
            write_json(self.data_file, data)
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
