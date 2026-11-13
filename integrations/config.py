"""Integration settings.

Every integration reads its settings through :func:`get`, never through
``os.getenv`` directly. Today values come from environment variables. When
the settings page lands, it can register a provider with
:func:`set_provider`; values it returns win over the environment, and any key
it does not know (returns ``None``) still falls back to the env var.

Settings are read on every use, so a change saved in the settings page takes
effect on the next poll or message without a restart.

``SCHEMA`` describes every key so a settings UI can render the fields
(label, type, default, whether the value is a secret) without hard-coding them.
"""
import os
import threading

_provider = None
_lock = threading.Lock()


def set_provider(fn):
    """Register ``fn(key) -> value | None`` as the primary settings source."""
    global _provider
    with _lock:
        _provider = fn


def get(key, default=None):
    provider = _provider
    if provider is not None:
        try:
            value = provider(key)
        except Exception as exc:  # noqa: BLE001  # a broken provider must not take integrations down
            print(f"[integrations] settings provider failed for {key}: {exc}")
            value = None
        if value is not None and value != '':
            return value
    value = os.getenv(key)
    if value is None or value == '':
        return default
    return value


def get_bool(key, default=False):
    value = get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def get_int(key, default, minimum=None):
    value = get(key)
    try:
        result = int(value) if value is not None else default
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    return result


# ── Schema (for the settings page) ────────────────────────────────────────────
SCHEMA = [
    # Live push
    {'key': 'LIVE_UPDATES_ENABLED', 'group': 'live', 'type': 'bool', 'default': True,
     'label': 'Live updates', 'help': 'Push changes and status updates to open browsers (Server-Sent Events).'},

    # Status monitor
    {'key': 'STATUS_MONITOR_ENABLED', 'group': 'monitor', 'type': 'bool', 'default': True,
     'label': 'Switch status monitor',
     'help': 'Poll LibreNMS in the background and detect switches going offline or online. Needs LibreNMS.'},
    {'key': 'STATUS_MONITOR_INTERVAL', 'group': 'monitor', 'type': 'int', 'default': 60,
     'label': 'Poll interval (seconds)', 'help': 'How often to ask LibreNMS for device status. Minimum 10.'},
    {'key': 'STATUS_MONITOR_CONFIRM', 'group': 'monitor', 'type': 'int', 'default': 2,
     'label': 'Polls to confirm a change',
     'help': 'A new status must be seen this many polls in a row before it counts, to ignore flapping.'},

    # Discord
    {'key': 'DISCORD_WEBHOOK_URL', 'group': 'discord', 'type': 'string', 'default': '', 'secret': True,
     'label': 'Discord webhook URL', 'help': 'Channel settings → Integrations → Webhooks → Copy URL.'},
    {'key': 'DISCORD_ALERTS_ENABLED', 'group': 'discord', 'type': 'bool', 'default': True,
     'label': 'Discord alerts', 'help': 'Post a message when a placed switch goes offline or comes back.'},
    {'key': 'DISCORD_NOTIFY_RECOVERY', 'group': 'discord', 'type': 'bool', 'default': True,
     'label': 'Notify on recovery', 'help': 'Also post when a switch comes back online.'},
    {'key': 'DISCORD_MENTION', 'group': 'discord', 'type': 'string', 'default': '',
     'label': 'Mention on outage', 'help': 'Optional text put in front of outage alerts, e.g. <@&ROLE_ID> or @here.'},
    {'key': 'DISCORD_USERNAME', 'group': 'discord', 'type': 'string', 'default': 'LAL Floor Plan',
     'label': 'Bot name', 'help': 'Name shown on the webhook messages.'},
    {'key': 'DISCORD_COOLDOWN', 'group': 'discord', 'type': 'int', 'default': 300,
     'label': 'Per-switch cooldown (seconds)', 'help': 'Do not alert about the same switch more often than this.'},

    # Seat → user / IP sources
    {'key': 'SEAT_SOURCES', 'group': 'seats', 'type': 'string', 'default': 'json',
     'label': 'Seat sources', 'help': 'Comma-separated, merged in order. Built in: json, http, checkin.'},
    {'key': 'SEAT_SOURCE_JSON_PATH', 'group': 'seats', 'type': 'string', 'default': 'seats.json',
     'label': 'Seat JSON file', 'help': 'Path of the static seat mapping file.'},
    {'key': 'SEAT_SOURCE_HTTP_URL', 'group': 'seats', 'type': 'string', 'default': '',
     'label': 'Seat HTTP source URL',
     'help': 'Endpoint returning {"seats": {"A-1": {"username": ..., "ip_address": ...}}}.'},
    {'key': 'SEAT_SOURCE_HTTP_TOKEN', 'group': 'seats', 'type': 'string', 'default': '', 'secret': True,
     'label': 'Seat HTTP source token', 'help': 'Sent as a Bearer token, if set.'},
    {'key': 'SEAT_SOURCE_CACHE_SECONDS', 'group': 'seats', 'type': 'int', 'default': 30,
     'label': 'Seat mapping cache (seconds)',
     'help': 'How long a merged mapping is reused before asking the sources again.'},

    # Seat check-in page
    {'key': 'CHECKIN_ENABLED', 'group': 'checkin', 'type': 'bool', 'default': False,
     'label': 'Seat check-in page',
     'help': 'Serve /checkin where people enter seat + username; their IP and MAC are recorded. Add "checkin" '
             'to Seat sources to use it.'},
    {'key': 'CHECKIN_ALLOWED_NETWORKS', 'group': 'checkin', 'type': 'string', 'default': '',
     'label': 'Allowed networks',
     'help': 'Comma-separated CIDRs players check in from, e.g. 10.0.0.0/16. Empty allows any.'},
    {'key': 'CHECKIN_TRUST_PROXY', 'group': 'checkin', 'type': 'bool', 'default': False,
     'label': 'Behind a reverse proxy',
     'help': 'Use X-Forwarded-For as the client IP. Only turn on if a proxy you control sets it.'},
    {'key': 'CHECKIN_VALIDATE_SEATS', 'group': 'checkin', 'type': 'bool', 'default': True,
     'label': 'Only accept seats on the plan', 'help': 'Reject seat numbers that are not in any seat block.'},
    {'key': 'CHECKIN_REFRESH_INTERVAL', 'group': 'checkin', 'type': 'int', 'default': 300,
     'label': 'Lease refresh (seconds)',
     'help': 'How often to re-check each MAC in LibreNMS and follow DHCP IP changes.'},
    {'key': 'CHECKIN_ADMIN_TOKEN', 'group': 'checkin', 'type': 'string', 'default': '', 'secret': True,
     'label': 'Admin token', 'help': 'If set, listing or deleting check-ins needs this token (X-Admin-Token header).'},
    {'key': 'CHECKIN_FILE', 'group': 'checkin', 'type': 'string', 'default': 'checkins.json',
     'label': 'Check-in data file', 'help': 'Where check-ins are stored.'},
    {'key': 'CHECKIN_HISTORY_ENABLED', 'group': 'checkin', 'type': 'bool', 'default': True,
     'label': 'Keep check-in history',
     'help': 'Log every check-in, seat move, removal and DHCP IP change, for /checkins/history and CSV export.'},
    {'key': 'CHECKIN_HISTORY_FILE', 'group': 'checkin', 'type': 'string', 'default': '',
     'label': 'Check-in history file',
     'help': 'Append-only JSON Lines log. Empty means next to the check-in data file (checkins-history.jsonl).'},

    # General
    {'key': 'PUBLIC_URL', 'group': 'general', 'type': 'string', 'default': '',
     'label': 'Public URL', 'help': 'Where people open the floor plan; used for links in alerts.'},
]


def describe():
    """Current values for every schema key, with secrets masked."""
    out = []
    for item in SCHEMA:
        raw = get(item['key'])
        entry = dict(item)
        entry['set'] = raw is not None
        if item.get('secret'):
            entry['value'] = '••••' if raw else ''
        elif item['type'] == 'bool':
            entry['value'] = get_bool(item['key'], item['default'])
        elif item['type'] == 'int':
            entry['value'] = get_int(item['key'], item['default'])
        else:
            entry['value'] = raw if raw is not None else item['default']
        out.append(entry)
    return out
