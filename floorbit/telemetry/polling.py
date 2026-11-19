"""Who polls the switches: LibreNMS or Telemetry (issue #945, docs/telemetry.md#who-polls).

LibreNMS polls the switches anyway when it runs, so Telemetry polling the same ports and walking
the same ARP and MAC tables only doubles the load on the access switches. With LibreNMS on,
Telemetry keeps what LibreNMS can't do: traps (instant port up/down), the device facts that fill
the inventory (discovery), gNMI and Cisco MDT streams, and the API pollers.

The choice is the telemetry plugin's ``polling`` setting:

- ``auto`` (default): LibreNMS when its plugin is on and has a URL and token, else Telemetry.
- ``librenms``: LibreNMS, even while it isn't set up yet.
- ``telemetry``: Telemetry polls everything and answers before LibreNMS.

Without LibreNMS polling, Telemetry walks the ARP and MAC tables every ``tables_minutes``
(0 = never). ``auto`` (the default): every 15 minutes while a segment has lookups on, because check-ins then
ask the switches for their one PC (issue #947, docs/segments.md); else every minute, because the
check-in pages answer from these tables alone.
"""
from floorbit.runtime import rt

CHOICES = ('auto', 'librenms', 'telemetry')
TABLES_MINUTES = 1             # no lookups: the tables are all the check-in pages have
TABLES_MINUTES_LOOKUPS = 15    # lookups on: the tables only feed history and the sweep


def _setting(registry, key):
    try:
        return registry.settings_store.get(f'plugin.telemetry.{key}') if registry is not None else None
    except Exception:   # noqa: BLE001 - a store that can't be read means the defaults
        return None


def choice(registry):
    value = str(_setting(registry, 'polling') or 'auto').strip().lower()
    return value if value in CHOICES else 'auto'


def librenms_on(registry):
    """The LibreNMS plugin is on and has a URL and a token."""
    spec = registry.specs.get('librenms') if registry is not None else None
    return bool(spec and registry.enabled(spec) and rt.librenms_enabled)


def _default_minutes():
    from floorbit import segments
    try:
        return TABLES_MINUTES_LOOKUPS if segments.lookups_on() else TABLES_MINUTES
    except Exception:  # noqa: BLE001  # no event data yet: the safe, fast default
        return TABLES_MINUTES


def tables_minutes(registry):
    value = _setting(registry, 'tables_minutes')
    try:
        return max(0, min(1440, int(value))) if value not in (None, '') else _default_minutes()
    except (TypeError, ValueError):
        return _default_minutes()


def plan(registry):
    """{who, why, tables_minutes}: who polls ports and tables, and why (shown on the status page)."""
    picked = choice(registry)
    if picked == 'telemetry':
        who, why = 'telemetry', 'set to Telemetry'
    elif picked == 'librenms':
        who, why = 'librenms', 'set to LibreNMS'
    elif librenms_on(registry):
        who, why = 'librenms', 'LibreNMS is on'
    else:
        who, why = 'telemetry', 'LibreNMS is off'
    return {'who': who, 'why': why, 'tables_minutes': 0 if who == 'librenms' else tables_minutes(registry)}


def apply(target_list, the_plan):
    """The targets as Telegraf should collect them under ``the_plan``: with LibreNMS polling, no port
    polls and no table walks; else table walks only when ``tables_minutes`` is above 0."""
    ports = the_plan['who'] != 'librenms'
    tables = ports and the_plan['tables_minutes'] > 0
    return [{**t, 'poll_ports': ports and t.get('poll_ports', True), 'tables': tables and t.get('tables', True)}
            for t in target_list]


def tables_interval(the_plan):
    minutes = the_plan['tables_minutes'] or TABLES_MINUTES
    return '60s' if minutes == 1 else f'{minutes}m'
