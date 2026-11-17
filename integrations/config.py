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
    {'key': 'DISCORD_STATUS_WEBHOOK_URL', 'group': 'discord', 'type': 'string', 'default': '', 'secret': True,
     'label': 'Attendee status channel webhook',
     'help': 'A webhook in a channel attendees read. Every update the crew posts on Network status goes '
             'there too, while the public status page is on. Leave empty to post nothing.'},
    {'key': 'DISCORD_SCHEDULE_WEBHOOK_URL', 'group': 'discord', 'type': 'string', 'default': '', 'secret': True,
     'label': 'Attendee programme channel webhook',
     'help': 'A webhook in a channel attendees read (it can be the status channel\'s). Shortly before a talk, '
             'tournament or meal starts, it is announced there, while the public schedule page is on.'},
    {'key': 'SCHEDULE_ANNOUNCE_MINUTES', 'group': 'discord', 'type': 'int', 'default': 10,
     'label': 'Announce the programme (minutes ahead)',
     'help': 'How long before an item starts it is announced in the programme channel. 0 announces nothing.'},
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
     'help': 'en (English), de-CH (Swiss German spelling) or de (German for Germany and Austria): alerts, '
             'the crew bot and the attendee channels. Slash command answers follow each user\'s Discord language.'},
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
     'help': 'Use X-Forwarded-For as the client IP (check-in, per-client limits). '
             'Only turn on if a proxy you control sets it.'},
    {'key': 'CHECKIN_VALIDATE_SEATS', 'group': 'checkin', 'type': 'bool', 'default': True,
     'label': 'Only accept seats on the plan', 'help': 'Reject seat numbers that are not in any seat block.'},
    {'key': 'CAPTIVE_ENABLED', 'group': 'checkin', 'type': 'bool', 'default': False,
     'label': 'Captive portal (DHCP option 114)',
     'help': 'Tell the local agent which machines checked in, so phones and laptops that did not see a quiet '
             '"sign in to network" note that opens the check-in page. Needs the check-in page, an agent with '
             'FLOORBIT_AGENT_CAPTIVE and option 114 in the event DHCP. Nothing is ever blocked.'},
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

    # General
    {'key': 'PUBLIC_URL', 'group': 'general', 'type': 'string', 'default': '',
     'label': 'Public URL', 'help': 'Where people open the floor plan; used for links in alerts.'},
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
