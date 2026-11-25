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


def public_url():
    """The Public URL setting, else where the crew last opened Floorbit (floorbit/public_url.py)."""
    from floorbit import public_url as learnt
    return learnt.get()


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

    # Service health wall
    {'key': 'HEALTH_INTERVAL', 'group': 'health', 'type': 'int', 'default': 30,
     'label': 'Check interval (seconds)', 'help': 'How often to ask the health plugins. Minimum 10.'},
    {'key': 'HEALTH_CONFIRM', 'group': 'health', 'type': 'int', 'default': 2,
     'label': 'Checks to confirm a change',
     'help': 'A service must show its new colour this many checks in a row before it alerts.'},

    # Security findings
    {'key': 'SECURITY_INTERVAL', 'group': 'health', 'type': 'int', 'default': 60,
     'label': 'Security check interval (seconds)',
     'help': 'How often to ask the security plugins for findings. Minimum 15.'},

    # Electrics
    {'key': 'POWER_ENABLED', 'group': 'power', 'type': 'bool', 'default': True,
     'label': 'Power layer',
     'help': 'The Electrics page and the power layer on the floor plan. Turn it off if nobody tracks power.'},
    {'key': 'POWER_WARN', 'group': 'power', 'type': 'int', 'default': 80,
     'label': 'Amber from (% of the fuse rating)', 'help': 'A circuit at this load shows amber.'},
    {'key': 'POWER_CRIT', 'group': 'power', 'type': 'int', 'default': 95,
     'label': 'Red from (% of the fuse rating)',
     'help': 'A circuit at this load shows red, files an incident and alerts, before the breaker trips.'},
    {'key': 'POWER_VOLTAGE', 'group': 'power', 'type': 'int', 'default': 230,
     'label': 'Voltage (V)', 'help': 'Turns readings in watts into amps.'},
    {'key': 'POWER_INTERVAL', 'group': 'power', 'type': 'int', 'default': 60,
     'label': 'Meter interval (seconds)', 'help': 'How often to ask the power plugins for readings. Minimum 15.'},
    {'key': 'POWER_TEAM', 'group': 'power', 'type': 'string', 'default': 'electrics',
     'label': 'Electrics team',
     'help': 'The team id power incidents go to. Its members may enter readings and trips.'},
    {'key': 'POWER_INCIDENTS', 'group': 'power', 'type': 'bool', 'default': True,
     'label': 'File power incidents',
     'help': 'A circuit turning red or a tripped breaker opens an incident for the Electrics team.'},

    # Discord
    {'key': 'DISCORD_WEBHOOK_URL', 'group': 'discord', 'type': 'string', 'default': '', 'secret': True,
     'label': 'Discord webhook URL', 'help': 'Channel settings → Integrations → Webhooks → Copy URL.'},
    {'key': 'DISCORD_ALERTS_ENABLED', 'group': 'discord', 'type': 'bool', 'default': True,
     'label': 'Discord alerts', 'help': 'Post a message when a placed switch goes offline or comes back.'},
    {'key': 'DISCORD_NOTIFY_RECOVERY', 'group': 'discord', 'type': 'bool', 'default': True,
     'label': 'Notify on recovery', 'help': 'Also post when a switch comes back online.'},
    {'key': 'DISCORD_MENTION', 'group': 'discord', 'type': 'string', 'default': '',
     'label': 'Mention on outage', 'help': 'Optional text put in front of outage alerts, e.g. <@&ROLE_ID> or @here.'},
    {'key': 'DISCORD_USERNAME', 'group': 'discord', 'type': 'string', 'default': 'Floorbit',
     'label': 'Bot name', 'help': 'Name shown on the webhook messages.'},
    {'key': 'DISCORD_LANGUAGE', 'group': 'discord', 'type': 'string', 'default': 'en',
     'label': 'Language of the messages',
     'help': 'en (English), de-CH (Swiss German spelling) or de (German for Germany and Austria): alerts '
             'and the crew bot. Slash command answers follow each user\'s Discord language.'},
    {'key': 'DISCORD_COOLDOWN', 'group': 'discord', 'type': 'int', 'default': 300,
     'label': 'Per-switch cooldown (seconds)', 'help': 'Do not alert about the same switch more often than this.'},
    {'key': 'ALERT_GROUP_AFTER', 'group': 'discord', 'type': 'int', 'default': 3,
     'label': 'Group switch alerts after',
     'help': 'More switch changes than this in one poll become one message, grouped by power circuit.'},
    {'key': 'ALERT_QUIET_HOURS', 'group': 'discord', 'type': 'string', 'default': '',
     'label': 'Quiet hours',
     'help': 'e.g. 02:00-08:00 (server time). Messages still go out, but silently and without the mention.'},
    {'key': 'DISCORD_HEALTH_ALERTS', 'group': 'discord', 'type': 'bool', 'default': True,
     'label': 'Health wall alerts',
     'help': 'Post when a service on the health wall goes red, and when it is back (with Notify on recovery).'},
    {'key': 'DISCORD_SECURITY_ALERTS', 'group': 'discord', 'type': 'bool', 'default': True,
     'label': 'Security alerts',
     'help': 'Post new high and medium security findings: where (switch, port, seat), never MACs or IPs.'},
    {'key': 'DISCORD_POWER_ALERTS', 'group': 'discord', 'type': 'bool', 'default': True,
     'label': 'Power alerts', 'help': 'Post when a circuit turns red or its breaker trips, with what it feeds.'},

    # The crew's Discord channel (integrations/crew.py)
    {'key': 'DISCORD_BOT_TOKEN', 'group': 'crew', 'type': 'string', 'default': '', 'secret': True,
     'label': 'Bot token',
     'help': 'Developer Portal → your app → Bot → Reset Token. The bot needs View Channel, Send Messages, '
             'Embed Links, Create Public Threads, Send Messages in Threads and Manage Threads in the crew channel.'},
    {'key': 'DISCORD_CREW_CHANNEL', 'group': 'crew', 'type': 'string', 'default': '',
     'label': 'Crew channel ID',
     'help': 'Right-click the channel → Copy Channel ID (turn on Developer Mode first). Incidents get a message '
             'and a thread here. Without a webhook URL, alerts go here too.'},
    {'key': 'DISCORD_APP_PUBLIC_KEY', 'group': 'crew', 'type': 'string', 'default': '',
     'label': 'App public key',
     'help': 'Developer Portal → General Information → Public Key. Turns on the Take it and Fixed buttons. '
             'Set the Interactions Endpoint URL there to <public URL>/api/discord/interactions.'},
    {'key': 'DISCORD_CREW_ENABLED', 'group': 'crew', 'type': 'bool', 'default': True,
     'label': 'Crew channel', 'help': 'Turn the crew channel off without removing the bot token.'},
    {'key': 'DISCORD_CREW_INCIDENTS', 'group': 'crew', 'type': 'bool', 'default': True,
     'label': 'Incidents in the crew channel',
     'help': 'Post each incident with a thread that follows it until it is fixed.'},
    {'key': 'DISCORD_CREW_NOTICES', 'group': 'crew', 'type': 'bool', 'default': True,
     'label': 'Crew notices in the crew channel',
     'help': 'Post each crew notice a lead puts up, so people away from Floorbit see it too.'},
    {'key': 'DISCORD_CREW_WAITING_MINUTES', 'group': 'crew', 'type': 'int', 'default': 10,
     'label': 'Nudge after (minutes)',
     'help': "Say once in an incident's thread when nobody has taken it for this long. 0 turns it off."},
    {'key': 'DISCORD_CREW_UNSEEN_MINUTES', 'group': 'crew', 'type': 'int', 'default': 5,
     'label': 'Say a sent job is unseen after (minutes)',
     'help': "Say once in an incident's thread when the tech it was sent to hasn't seen it for this long. "
             '0 turns it off.'},
    {'key': 'DISCORD_CREW_WAITING_ROLE', 'group': 'crew', 'type': 'string', 'default': '',
     'label': 'Role to ping when waiting',
     'help': 'Optional. Right-click the role in Server Settings → Roles → Copy Role ID. Its members get '
             'pinged by that one line, for example the leads.'},

    # Seat → user / IP sources
    {'key': 'SEAT_SOURCES', 'group': 'seats', 'type': 'string', 'default': 'json',
     'label': 'Seat sources', 'help': 'Comma-separated, merged in order. Built in: json, http, checkin.'},
    {'key': 'SEAT_SOURCE_JSON_PATH', 'group': 'seats', 'type': 'string', 'default': '',
     'label': 'Seat JSON file',
     'help': 'Path of the static seat mapping file. Empty: seats.json next to data.json.'},
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
    {'key': 'CHECKIN_ADDRESS', 'group': 'checkin', 'type': 'string', 'default': '',
     'label': 'Short check-in address',
     'help': 'A name people can type on their PC, e.g. checkin.lan: point it at Floorbit in the event DNS. '
             'It goes on the seat cards and the sign-in page, and opening it lands on /checkin.'},
    {'key': 'CHECKIN_REQUIRE_PIN', 'group': 'checkin', 'type': 'bool', 'default': False,
     'label': 'Always ask for the seat PIN',
     'help': 'Each seat card shows a 5-character PIN; on a PC people type the PIN and their nick, and the PIN '
             'names the seat. When on, typing a seat number without its PIN is refused too.'},
    {'key': 'CHECKIN_ALLOWED_NETWORKS', 'group': 'checkin', 'type': 'string', 'default': '',
     'label': 'Allowed networks',
     'help': 'Comma-separated CIDRs players check in from, e.g. 10.0.0.0/16. Empty allows any.'},
    {'key': 'CHECKIN_TRUST_PROXY', 'group': 'checkin', 'type': 'bool', 'default': False,
     'label': 'Behind a reverse proxy',
     'help': 'Use X-Forwarded-For as the client IP for per-client limits and the sign-in lockout. '
             "Check-in takes the PC's address only from the local agent's front door. "
             'Only turn on if a proxy you control sets it.'},
    {'key': 'CHECKIN_PROXY_HOPS', 'group': 'checkin', 'type': 'int', 'default': 1,
     'label': 'Proxies in front',
     'help': 'How many proxies you control add to X-Forwarded-For (e.g. 2 for a CDN in front of the '
             'ingress). Only used behind a reverse proxy.'},
    {'key': 'CHECKIN_VALIDATE_SEATS', 'group': 'checkin', 'type': 'bool', 'default': True,
     'label': 'Only accept seats on the plan', 'help': 'Reject seat numbers that are not in any seat block.'},
    {'key': 'CHECKIN_VERIFY_RATE', 'group': 'checkin', 'type': 'int', 'default': 10,
     'label': 'Port lookups per second',
     'help': 'How many check-ins a second the background looks up in the monitoring source. A burst of '
             'check-ins waits its turn instead of flooding LibreNMS.'},
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

    # Port trouble
    {'key': 'ATTENTION_INTERVAL', 'group': 'attention', 'type': 'int', 'default': 120,
     'label': 'Port read (seconds)',
     'help': 'How often every access port is read for port trouble: flapping, errors rising, half duplex. Minimum 30.'},
    {'key': 'ATTENTION_FLAPS', 'group': 'attention', 'type': 'int', 'default': 3,
     'label': 'Link changes that count as flapping',
     'help': 'This many link ups and downs within 10 minutes put a port on the list.'},
    {'key': 'ATTENTION_ERRORS', 'group': 'attention', 'type': 'int', 'default': 10,
     'label': 'Errors per read',
     'help': 'A port whose error counter rises by this much between two reads is listed.'},

    # Logs
    {'key': 'SYSLOG_ALLOW', 'group': 'syslog', 'type': 'string', 'default': '',
     'label': 'Allowed senders',
     'help': 'Comma-separated addresses or CIDRs that may send syslog, besides the switches on the plan. Empty: only '
             'the switches.'},
    {'key': 'SYSLOG_ALLOW_SWITCHES', 'group': 'syslog', 'type': 'bool', 'default': True,
     'label': 'Accept the switches on the plan',
     'help': 'Lines from the management address of every switch in the inventory are accepted.'},
    {'key': 'SYSLOG_RATE', 'group': 'syslog', 'type': 'int', 'default': 200,
     'label': 'Lines per second per sender',
     'help': "More from one sender in a second are dropped and counted, so one chatty box can't flood the page."},
    {'key': 'SYSLOG_RETENTION_HOURS', 'group': 'syslog', 'type': 'int', 'default': 24,
     'label': 'Keep lines (hours)',
     'help': 'How long log lines are kept for the Logs page.'},
    {'key': 'SYSLOG_MAX_LINES', 'group': 'syslog', 'type': 'int', 'default': 50000,
     'label': 'Lines kept at most',
     'help': 'Older lines go first when there are more.'},
    {'key': 'SYSLOG_MAX_MB', 'group': 'syslog', 'type': 'int', 'default': 100,
     'label': 'Log size at most (MB)',
     'help': 'The stored log is cut back to this size.'},
    {'key': 'LOG_ALERT_MINUTES', 'group': 'syslog', 'type': 'int', 'default': 15,
     'label': 'Repeat a log alert after (minutes)',
     'help': 'The same log alert on the same box is sent again only after this long.'},

    # DNS, games and bandwidth
    {'key': 'DNS_INTERVAL', 'group': 'insights', 'type': 'int', 'default': 60,
     'label': 'DNS log read (seconds)',
     'help': "How often the DNS plugins' query logs are read."},
    {'key': 'DNS_MIN_SEATS', 'group': 'insights', 'type': 'int', 'default': 5,
     'label': 'Seats before a domain is named',
     'help': 'A domain shows on the DNS page only once this many different clients looked it up, so nobody '
             'can be singled out. 5 at least.'},
    {'key': 'DNS_RETENTION_HOURS', 'group': 'insights', 'type': 'int', 'default': 168,
     'label': 'Keep DNS counts (hours)',
     'help': 'How long the hall-wide DNS counts are kept.'},
    {'key': 'LANCACHE_INTERVAL', 'group': 'insights', 'type': 'int', 'default': 30,
     'label': 'LAN cache log read (seconds)',
     'help': "How often the LAN cache's access log is read for the Games page."},
    {'key': 'LANCACHE_RETENTION_HOURS', 'group': 'insights', 'type': 'int', 'default': 168,
     'label': 'Keep LAN cache counts (hours)',
     'help': 'How long downloads per game are kept.'},
    {'key': 'STATS_UPLINK_PATTERN', 'group': 'insights', 'type': 'string', 'default': '',
     'label': 'Uplink port names',
     'help': 'A regular expression for port descriptions that mark uplinks, for the bandwidth figures. Empty: uplink '
             'or trunk.'},
    {'key': 'FORECAST_CAPACITY_MBPS', 'group': 'insights', 'type': 'int', 'default': 0,
     'label': 'Internet line (Mbit/s)',
     'help': "The event's internet bandwidth, for the forecast. 0 turns the forecast warning off."},
    {'key': 'FORECAST_WARN_PERCENT', 'group': 'insights', 'type': 'int', 'default': 80,
     'label': 'Warn at (% of the line)',
     'help': 'Warn when the forecast reaches this share of the line.'},
    {'key': 'FORECAST_LEAD_HOURS', 'group': 'insights', 'type': 'int', 'default': 3,
     'label': 'Look ahead (hours)',
     'help': 'How far ahead the forecast warns.'},

    # Discord
    {'key': 'DISCORD_FORECAST_ALERTS', 'group': 'discord', 'type': 'bool', 'default': True,
     'label': 'Post forecast warnings',
     'help': 'Post to Discord when the bandwidth forecast expects the line to fill up.'},

    # Health
    {'key': 'GAME_INTERVAL', 'group': 'health', 'type': 'int', 'default': 30,
     'label': 'Game server query (seconds)',
     'help': 'How often each game server is asked for players and map.'},
    {'key': 'SERVICES_INTERVAL', 'group': 'health', 'type': 'int', 'default': 30,
     'label': 'Service check (seconds)',
     'help': 'How often DNS, DHCP and the other services are checked.'},

    # Switch configs and terminal
    {'key': 'CONFIG_BACKUP_HOUR', 'group': 'switchtools', 'type': 'string', 'default': '',
     'label': 'Nightly config backup (hour)',
     'help': 'The hour (0-23) the switch configs are saved each night, or off.'},
    {'key': 'CONFIG_KEEP', 'group': 'switchtools', 'type': 'int', 'default': 50,
     'label': 'Config copies kept per switch',
     'help': 'Older copies are deleted.'},
    {'key': 'TERMINAL_IDLE_MINUTES', 'group': 'switchtools', 'type': 'int', 'default': 10,
     'label': 'Close an idle terminal after (minutes)',
     'help': 'A switch terminal with no typing for this long is closed.'},
    {'key': 'TERMINAL_MAX_MINUTES', 'group': 'switchtools', 'type': 'int', 'default': 60,
     'label': 'Longest terminal session (minutes)',
     'help': 'A switch terminal is closed after this long in any case.'},

    # Backups to an S3 bucket (floorbit/s3_backup.py)
    {'key': 'S3_BACKUP_ENDPOINT', 'group': 'backup', 'type': 'string', 'default': '',
     'label': 'S3 endpoint',
     'help': 'The S3 address of MinIO, Garage, Backblaze B2 or another store, like https://s3.example.com. Empty: '
             'Amazon S3.'},
    {'key': 'S3_BACKUP_REGION', 'group': 'backup', 'type': 'string', 'default': 'us-east-1',
     'label': 'Region', 'help': "The bucket's region, like eu-central-1. Most other stores take us-east-1."},
    {'key': 'S3_BACKUP_BUCKET', 'group': 'backup', 'type': 'string', 'default': '',
     'label': 'Bucket', 'help': 'Empty turns S3 backups off.'},
    {'key': 'S3_BACKUP_PREFIX', 'group': 'backup', 'type': 'string', 'default': 'floorbit/',
     'label': 'Folder in the bucket',
     'help': 'Backups go here. Only files Floorbit made here are listed and deleted.'},
    {'key': 'S3_BACKUP_ACCESS_KEY', 'group': 'backup', 'type': 'string', 'default': '', 'secret': True,
     'label': 'Access key ID', 'help': 'Give the key only list, read, write and delete in this bucket.'},
    {'key': 'S3_BACKUP_SECRET_KEY', 'group': 'backup', 'type': 'string', 'default': '', 'secret': True,
     'label': 'Secret access key', 'help': 'Stored encrypted and never shown again.'},
    {'key': 'S3_BACKUP_PASSPHRASE', 'group': 'backup', 'type': 'string', 'default': '', 'secret': True,
     'label': 'Encryption passphrase',
     'help': 'Set it to encrypt each backup before it leaves, so the bucket only holds what nobody can read. '
             'Keep a copy elsewhere: without it, encrypted backups cannot be restored.'},
    {'key': 'S3_BACKUP_INTERVAL_HOURS', 'group': 'backup', 'type': 'int', 'default': 24,
     'label': 'Back up every (hours)', 'help': '0: only when someone presses Back up now.'},
    {'key': 'S3_BACKUP_KEEP', 'group': 'backup', 'type': 'int', 'default': 30,
     'label': 'Backups kept', 'help': 'After each upload, older backups in the folder are deleted.'},

    # Check-in
    {'key': 'CHECKIN_PIN_TRIES', 'group': 'checkin', 'type': 'int', 'default': 10,
     'label': 'Wrong PINs before a pause',
     'help': 'After this many wrong PINs from one address, check-in pauses for it.'},

    # Seats
    {'key': 'SEAT_SOURCE_HTTP_VERIFY_SSL', 'group': 'seats', 'type': 'bool', 'default': True,
     'label': "Verify the HTTP source's TLS certificate",
     'help': 'Turn off only for a source with a self-signed certificate on the event network.'},

    # General
    {'key': 'INVENTORY_SYNC_MINUTES', 'group': 'general', 'type': 'int', 'default': 0,
     'label': 'Inventory sync (minutes)',
     'help': 'How often the inventory plugins (NetBox) are synced on their own, 5 or more. 0 is off: only Sync now.'},
    {'key': 'DISCOVERY_MINUTES', 'group': 'general', 'type': 'int', 'default': 15,
     'label': 'Discovery (minutes)',
     'help': 'How often inventory devices are filled from the monitoring source (model, serial, software, memory, '
             'disks, location, interfaces), 5 or more. Values set by hand stay. 0 is off: only Sync now.'},
    {'key': 'PUBLIC_URL', 'group': 'general', 'type': 'string', 'default': '',
     'label': 'Public URL', 'help': 'Where people open the floor plan; used for links in alerts. Empty: the address '
             'the crew last opened Floorbit at.'},
    {'key': 'QR_URL', 'group': 'general', 'type': 'string', 'default': '',
     'label': 'Address on the seat QR codes',
     'help': 'Where the QR codes on the seat cards point, e.g. http://help.lan when attendees reach Floorbit '
             'under another name than the crew. Empty uses the public URL. Reprint the cards after a change.'},
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
