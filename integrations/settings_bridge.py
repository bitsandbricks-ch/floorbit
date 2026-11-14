"""Connect the integrations to the persisted settings store (the /settings page).

When the app has a ``settings_store`` (see ``settings_store.py``), this:

1. adds a section per integration and a field per setting in
   ``integrations.config.SCHEMA`` to the store's ``SECTIONS`` / ``FIELDS``,
   so the settings page renders and saves them with no extra UI code;
2. registers a provider on ``integrations.config`` so a value saved on the
   settings page wins over the env var. That covers the store's own fields
   too, e.g. ``LIBRENMS_URL`` saved as ``librenms.url``.

Values that were never saved still come from the env var and then the
integration's default, exactly as without the store.
"""
import sys

from . import config

SECTIONS = [
    {'id': 'live', 'title': 'Live updates',
     'description': 'Push changes and switch status to every open browser without a reload.'},
    {'id': 'monitor', 'title': 'Status monitor',
     'description': 'Background LibreNMS poll that detects switches going offline or coming back.'},
    {'id': 'health', 'title': 'Health wall and security',
     'description': ('How often the health plugins (DHCP, DNS, cache, game servers, uplink) and the '
                     'security plugins are asked.')},
    {'id': 'power', 'title': 'Electrics',
     'description': 'Power boards and circuits: when a circuit counts as loaded, and where its incidents go.'},
    {'id': 'discord', 'title': 'Discord alerts',
     'description': 'Post to a Discord channel when placed switches go offline or recover.'},
    {'id': 'seats', 'title': 'Seat sources',
     'description': 'Where the seat to user / IP mapping comes from. Sources are merged in the order listed.'},
    {'id': 'checkin', 'title': 'Seat check-in',
     'description': ('A /checkin page where players enter seat and username; '
                     'their IP and MAC (from LibreNMS ARP) are recorded.')},
    {'id': 'general', 'title': 'General', 'description': 'Shared settings for integrations.'},
]

# Keys whose comma-separated value is better edited as a list
LIST_KEYS = {'SEAT_SOURCES', 'CHECKIN_ALLOWED_NETWORKS'}
URL_KEYS = {'SEAT_SOURCE_HTTP_URL', 'PUBLIC_URL'}
INT_LIMITS = {
    'STATUS_MONITOR_INTERVAL': (10, 86400),
    'STATUS_MONITOR_CONFIRM': (1, 20),
    'DISCORD_COOLDOWN': (0, 86400),
    'ALERT_GROUP_AFTER': (1, 10),
    'HEALTH_INTERVAL': (10, 86400),
    'HEALTH_CONFIRM': (1, 20),
    'SECURITY_INTERVAL': (15, 86400),
    'POWER_WARN': (10, 150),
    'POWER_CRIT': (11, 200),
    'POWER_VOLTAGE': (100, 400),
    'POWER_INTERVAL': (15, 86400),
    'SEAT_SOURCE_CACHE_SECONDS': (0, 86400),
    'CHECKIN_REFRESH_INTERVAL': (30, 86400),
}


def field_key(env_key):
    return 'integrations.' + env_key.lower()


def store_fields():
    fields = []
    for item in config.SCHEMA:
        key = item['key']
        if item.get('secret'):
            ftype = 'secret'
        elif key in LIST_KEYS:
            ftype = 'list'
        elif key in URL_KEYS:
            ftype = 'url'
        elif item['type'] in ('bool', 'int'):
            ftype = item['type']
        else:
            ftype = 'text'
        default = item['default']
        if ftype == 'list':
            default = [p.strip() for p in str(default).split(',') if p.strip()]
        field = dict(key=field_key(key), section=item['group'], label=item['label'],
                     type=ftype, env=key, default=default, help=item.get('help'))
        if ftype == 'int':
            field['min'], field['max'] = INT_LIMITS.get(key, (0, 10 ** 9))
            if 'seconds' in item['label'].lower():
                field['unit'] = 'seconds'
        fields.append(field)
    return fields


def connect(store):
    """Register integration fields with ``store`` and read saved values from it."""
    module = sys.modules.get(type(store).__module__)
    if module is None or not hasattr(module, 'FIELDS'):
        return False

    known_sections = {s['id'] for s in module.SECTIONS}
    module.SECTIONS.extend(s for s in SECTIONS if s['id'] not in known_sections)
    known_fields = set(module.FIELDS_BY_KEY)
    for field in store_fields():
        if field['key'] not in known_fields:
            module.FIELDS.append(field)
            module.FIELDS_BY_KEY[field['key']] = field
    store.reload()   # pick up values saved for the fields we just added

    by_env = {f['env']: f['key'] for f in module.FIELDS if f.get('env')}

    def provider(env_key):
        key = by_env.get(env_key)
        if key is None:
            return None
        store.reload_if_changed()
        if store.source(key) != 'saved':
            return None   # let config fall back to env, then the integration default
        value = store.get(key)
        if isinstance(value, list):
            value = ','.join(value)
        return value

    config.set_provider(provider)
    return True
