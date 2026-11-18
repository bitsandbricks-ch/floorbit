# Integrations

Everything lives in the `integrations/` package and is wired into `app.py` with one call:

```python
from integrations import init_integrations
init_integrations(app, load_data=load_data)
```

Each integration reads its settings through `integrations.config`. `GET /api/integrations` returns
`settings`, a schema of every key (label, type, default, whether it's secret, current value with
secrets masked), and the settings page renders its fields from it.

## Where a setting lives

Most settings are on the **Settings** page, stored in the database (or `data.json`) and in the audit
log when they change. Each one still has its environment variable:

1. a value saved on the Settings page wins,
2. otherwise the environment variable,
3. otherwise the default.

So an existing `.env` keeps working as it is: nothing has to be imported, and the page shows where each
value comes from. Saving a field overrides the env var; clearing it goes back to the env var. Secrets
(tokens, passwords) are write-only on the page.

These stay in the environment only, because they are needed before the database is open, or because
whoever runs the server sets them and an admin of the app must not be able to change them:

| Setting | Why it isn't on the page |
| --- | --- |
| `FLOORBIT_DATABASE_URL`, `FLOORBIT_DATA_FILE`, `REDIS_*`, `FLOORBIT_CLUSTER` | needed before settings can be read |
| `SECRET_KEY`, `AUTH_ADMIN_USER`, `AUTH_ADMIN_PASSWORD`, `OIDC_*_CLIENT_SECRET` | sign-in: the session key, the first admin, the OIDC client secrets |
| `FLOORBIT_SECRET_KEY_FILE`, `FLOORBIT_SECRET_OLD_KEY_FILES` | the key stored logins and passwords are encrypted with ([credentials.md](credentials.md)) |
| `TZ`, `FLOORBIT_PORT`, `FLOORBIT_VERSION` | the container itself |
| `OUTBOUND_BLOCK_NETS`, `PROBE_NETS` | where a hosted server may send requests: the host's choice, not the event's |
| `SYSLOG_ENABLED`, `SYSLOG_PORT`, `SYSLOG_TCP`, `SYSLOG_BIND`, `FLOWS_*` | listeners that open a port when the server starts |
| `LANCACHE_LOG`, `LANCACHE_CACHE_DIR`, `MONITORING_CACHE_FILE`, `AUDIT_FILE` and the other state paths | paths inside the container |
| `FLOORBIT_DEMO`, `SCREENSHOT_*` | demo and screenshot runs |

## Live push updates

Browsers subscribe to `GET /api/events` (Server-Sent Events). The React app handles it
(`frontend/src/api/live.ts`); the kiosk (`static/js/kiosk.js`) and notifications (`static/js/notify.js`)
listen on their own:

| Event | When | Frontend effect |
|---|---|---|
| `hello` | on connect | applies the monitor's last known statuses |
| `switch.status` | a switch changed status | updates its dot and the hero counts |
| `data.changed` | someone added/moved/renamed/deleted a switch or seat block | reloads that list (skips your own edits, waits until you stop dragging) |
| `monitor.poll` | every status poll | none (re-dispatched only) |
| `checkin`, `checkin.removed`, `checkin.refreshed` | seat check-ins change | none (re-dispatched only) |
| `attention.changed` | the needs-attention list changed | the Problems page reloads |
| `stats.changed` | a new read of all ports, or the peak was reset | the Stats page reloads |

| Variable | Default | |
|---|---|---|
| `LIVE_UPDATES_ENABLED` | `true` | |

The event bus is in-process. That matches how the app runs (`python app.py`, threaded). If it
ever runs as several worker processes, `events.publish` is the one place to add Redis pub/sub.
Behind nginx, the stream sends `X-Accel-Buffering: no`; also set `proxy_read_timeout` above 15s.

**How many at once.** Each open stream holds one of the server's threads until its tab closes. So
that pages always load, Floorbit takes streams only up to three quarters of the threads (48 of the
image's 64; `gunicorn.conf.py` tells it the count), and readers who aren't signed in, such as
attendees on the status page, get at most half of those. One more is refused with `503`
`{"code": "live_full"}`: the page works but doesn't update by itself, and asks again after 20 to
40 seconds. More threads (`GUNICORN_CMD_ARGS=--threads 200`) mean more streams.

## Switch status monitor

A background thread polls the monitoring plugin (LibreNMS: `/api/v0/devices`, one request for all devices) every
interval, matches devices to the switches placed on the plan (same name matching as the rest
of the app), and publishes `switch.status` when one changes. The first poll is a baseline
(no alerts after a restart), and a change must be seen on N polls in a row to count. When the
monitoring source itself stops answering, the monitor sends one `monitoring.offline` event (one
Discord message) instead of switch alerts, and starts from a fresh baseline when it is back; see
[offline.md](offline.md).

| Variable | Default | |
|---|---|---|
| `STATUS_MONITOR_ENABLED` | `true` | needs `LIBRENMS_URL` + `LIBRENMS_TOKEN` |
| `STATUS_MONITOR_INTERVAL` | `60` | seconds, min 10 |
| `STATUS_MONITOR_CONFIRM` | `2` | polls in a row before a change counts |
| `HEALTH_INTERVAL` | `30` | seconds between health wall checks, min 10 ([health.md](health.md)) |
| `HEALTH_CONFIRM` | `2` | checks in a row before a service's new colour counts |
| `SECURITY_INTERVAL` | `60` | seconds between security checks, min 15 ([security.md](security.md)) |
| `POWER_INTERVAL` | `60` | seconds between power meter readings, min 15 ([power.md](power.md)) |

`GET /api/status/snapshot` returns the last known status of every placed switch in one call.
`POST /api/integrations/monitor/poll` runs a poll now.

## Discord alerts

Posts to a channel webhook when placed switches go offline or come back. All changes from one
poll go in one message, grouped by power circuit past `ALERT_GROUP_AFTER`, so a row losing power is
one message. Muted switches send nothing ([alerts.md](alerts.md)).

| Variable | Default | |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | | Channel settings → Integrations → Webhooks |
| `DISCORD_ALERTS_ENABLED` | `true` | |
| `DISCORD_STATUS_WEBHOOK_URL` | | a webhook in a channel attendees read: every update the crew posts on the network status page goes there too, while the public page is on ([status-page.md](status-page.md#discord)) |
| `DISCORD_SCHEDULE_WEBHOOK_URL` | | a webhook in a channel attendees read: what is about to start on the public programme is announced there ([schedule.md](schedule.md#discord)) |
| `SCHEDULE_ANNOUNCE_MINUTES` | `10` | how long before an item starts it is announced; `0` announces nothing |
| `DISCORD_NOTIFY_RECOVERY` | `true` | also post "back online" with downtime, and how many open incidents from its seats were filed while it was down |
| `DISCORD_MENTION` | | e.g. `<@&ROLE_ID>` or `@here`, outages only |
| `DISCORD_USERNAME` | `Floorbit` | |
| `DISCORD_LANGUAGE` | `en` | `de-CH` or `de` for German: alerts, the crew bot and the attendee channels. Slash command answers follow each user's own Discord language ([crew-discord.md](crew-discord.md#language)) |
| `DISCORD_COOLDOWN` | `300` | seconds between outage alerts for the same switch |
| `ALERT_GROUP_AFTER` | `3` | more switch changes than this in one poll become one message, grouped by power circuit ([alerts.md](alerts.md)) |
| `ALERT_QUIET_HOURS` | | e.g. `02:00-08:00`: messages go out silently and without the mention |
| `ATTENTION_INTERVAL` | `120` | seconds between reads of every port for the needs-attention list (at least 30; [alerts.md](alerts.md#needs-attention)) |
| `ATTENTION_FLAPS` | `3` | link changes within ten minutes that count as flapping |
| `ATTENTION_ERRORS` | `10` | interface errors gained since the last read that count as rising |
| `SEAT_FINDER` | `true` | the public "find your seat" page `/find` ([kiosk.md](kiosk.md#find-your-seat)) |
| `SEAT_FINDER_NICKS` | `false` | let `/find` also find a seat by the exact nick |
| `CABLE_AUTO` | `true` | draw a cable to every seat whose switch port is known ([cables.md](cables.md#cables-drawn-on-the-floor-plan)); also under Settings > Cabling |
| `ATTENDEE_VIEW` | `false` | the public attendee view `/hall`, seats online or offline ([kiosk.md](kiosk.md#attendee-view)); also under Settings > Attendee pages |
| `STATUS_PAGE` | `false` | the public network status page `/status` ([status-page.md](status-page.md)); also under Settings > Attendee pages |
| `STATUS_SWITCH_NAMES` | `false` | name the switches that are down on `/status` |
| `METRICS_ENABLED` | `false` | Prometheus metrics at `/api/metrics` ([metrics.md](metrics.md)); also under Settings > Prometheus metrics |
| `SCHEDULE_PAGE` | `false` | the public schedule and countdown `/agenda` ([schedule.md](schedule.md)); also under Settings > Attendee pages |
| `SPEEDTEST`, `SPEEDTEST_MAX_RUNNING`, `SPEEDTEST_TEST_MB`, `SPEEDTEST_SEAT_MINUTES`, `SPEEDTEST_MAX_MBPS` | on, 3, 250, 10, 1000 | the speed test on the seat help page and its limits ([speedtest.md](speedtest.md#limits)); also under Settings > Speed tests |
| `STATS_WALL` | `false` | the public stats wall `/wall` ([stats-wall.md](stats-wall.md)); also under Settings > Attendee pages |
| `STATS_UPLINK_PATTERN` | `uplink\|trunk` | port descriptions that mark a switch's uplink on the [stats dashboard](stats.md) (a regular expression, case-insensitive) |
| `DISCORD_HEALTH_ALERTS` | `true` | post when a service on the health wall goes red, and when it is back |
| `DISCORD_SECURITY_ALERTS` | `true` | post new high and medium security findings (where, never MACs or IPs) |
| `DISCORD_POWER_ALERTS` | `true` | post when a circuit turns red or its breaker trips, with what it feeds |
| `PUBLIC_URL` | | link in the alert |

`POST /api/integrations/discord/test` sends a test message.

With no webhook, alerts can go to the crew channel through a bot instead. That channel also gets
one message and thread per incident ([crew-discord.md](crew-discord.md)).

## Seat → user / IP sources

`/api/seats/info`, `/api/seats/resolve` and `/api/seats/heatmap` get their seat mapping from
`integrations.seat_sources` instead of reading `seats.json` directly. Sources are merged in
the order listed in `SEAT_SOURCES`; the first one with a value for a field wins. Hand entries
from the [seat mapping](seat-mapping.md) page and plugins with `uses: [mapping]` always come
before them.

`/api/seats/resolve` and `/api/seats/heatmap` look up each seat's IP in the monitoring source in
parallel (eight at a time). A lookup that fails marks only that seat (`resolved: false` with the
error); the rest of the answer is still there.

| Source | What it reads |
|---|---|
| `json` | `SEAT_SOURCE_JSON_PATH` (default `seats.json`), the current behaviour |
| `http` | `SEAT_SOURCE_HTTP_URL` returning `{"seats": {"A-1": {"username": "...", "ip_address": "..."}}}`, optional `SEAT_SOURCE_HTTP_TOKEN` (Bearer) |
| `checkin` | the seat check-in page below |

Adding a source (DHCP leases, an event backend, …):

```python
from integrations import seat_sources

@seat_sources.register
class DhcpSource(seat_sources.SeatSource):
    name = 'dhcp'
    label = 'DHCP leases'

    def fetch(self):
        return {'A-1': {'username': None, 'ip_address': '10.0.1.11'}}
```

then add `dhcp` to `SEAT_SOURCES`. `GET /api/seats/sources` lists sources and their last errors.

## Seat check-in page

`/checkin` asks for seat and username. The server records the request's IP, looks up its MAC in
LibreNMS ARP data, and stores one row per seat (seat, username, IP, MAC). A background job
follows DHCP changes by asking LibreNMS which IP each MAC has now. Add `checkin` to
`SEAT_SOURCES` (e.g. `checkin,json`) to use it on the plan.

| Variable | Default | |
|---|---|---|
| `CHECKIN_ENABLED` | `false` | |
| `CHECKIN_ALLOWED_NETWORKS` | | CIDRs, e.g. `10.0.0.0/16`. Rejects check-ins from elsewhere (VPN, NAT, guest Wi-Fi) |
| `CHECKIN_TRUST_PROXY` | `false` | use `X-Forwarded-For` for check-ins and the per-client limits (help page, speed test, seat finder, sign-in lockout); only behind a proxy you control |
| `CHECKIN_PROXY_HOPS` | `1` | how many proxies you control append to `X-Forwarded-For`; the client is that many entries from the right, so an address the client sends itself is ignored |
| `CHECKIN_VALIDATE_SEATS` | `true` | only accept seats that exist in seat blocks |
| `SEAT_WALK_AGENT_URL` | | where laptops in the hall reach the local agent's captive port, for the [seat walk-through](seat-walk.md); empty takes what the agent reports (`FLOORBIT_AGENT_LAN_URL`) |
| `CHECKIN_REFRESH_INTERVAL` | `300` | seconds between MAC → IP refreshes |
| `CHECKIN_VERIFY_RATE` | `10` | port lookups a second for new check-ins; a burst waits its turn ([sizing](sizing.md#doors-open)) |
| `CAPTIVE_ENABLED` | `false` | answer the agents' captive portal (DHCP option 114), see below |
| `CHECKIN_ADMIN_TOKEN` | | if set, `GET/DELETE /api/checkins` need `X-Admin-Token` |
| `CHECKIN_FILE` | `checkins.json` | |

The page is in English and German and made for phones. While check-in is off it says so, with
the event's start from the schedule when that is still ahead. When it is on, the sign-in page,
where attendees land, leads with a big "Check in to your seat" button above the crew's sign-in.

Endpoints: `POST /api/checkin`, `GET /api/checkin/info` (open or not, when it opens, this
device's check-in), `GET /api/checkin/me`, `GET /api/checkins` (the
user/IP/seat/MAC table), `DELETE /api/checkins/<seat>`, `POST /api/checkins/refresh`.

### The "sign in to network" note (Captive Portal API)

With a [local agent](agent.md), phones and laptops can be reminded to check in without blocking
anything. It is off until you turn on **Captive portal (DHCP option 114)** in the check-in
settings (`CAPTIVE_ENABLED`); until then agents asking get a 409 and say nothing. Turn on the
**Check-in note on phones** plugin under Settings > Plugins with the address the agent answers on
(`0.0.0.0:8908`), or set `FLOORBIT_AGENT_CAPTIVE=0.0.0.0:8908` on the agent (one or the other), and
let your DHCP server hand out
option 114 (RFC 8910) with the URL of the agent's `/.well-known/captive-portal`. Clients that
support it ask that URL, and until their seat has checked in they show a quiet "sign in to
network" note that opens the check-in page. Gaming PCs that ignore it lose nothing, because
traffic is never held back.

- **Done means the seat, not the machine.** A client counts as checked in when its IP belongs to a
  checked-in seat: the IP its check-in has now (the refresh follows the MAC to a new lease), or any
  IP on that seat's cabled port in the last MAC table read. A reboot, a new lease or a new MAC
  doesn't bring the note back. Reading the MAC tables runs every two minutes in the background
  while the agent asks ([sizing](sizing.md)).
- **When in doubt, say nothing.** Until the agent has heard from the hosted Floorbit, while
  check-in is off, or with no `PUBLIC_URL` set, every answer is `"captive": false`. When the hosted
  side is away, the agent keeps answering from what it heard last.
- **HTTPS.** RFC 8908 wants HTTPS for this URL, so serve it through the event's reverse proxy with a
  certificate. Put that proxy's address in `FLOORBIT_AGENT_CAPTIVE_PROXIES` so the client's IP comes
  from `X-Forwarded-For` (the plugin's *Reverse proxy addresses*).
- The note opens `PUBLIC_URL/checkin`, or the plugin's *Sign-in page* (`FLOORBIT_AGENT_CAPTIVE_PORTAL_URL`
  on the agent) when it is set.
- How well clients follow it varies: phones and Macs do, Windows only partly. Check it on your own
  devices before the event.

### Check-in history and CSV export

Every change to the check-in table is appended to a JSON Lines log: `checkin`, `moved`
(the same machine checked in at another seat, `to_seat`), `removed`, `ip_changed` (DHCP,
`previous_ip`) and `mac_found`. The **History** tab of the crew Check-in page (`/checkins?tab=history`; `/checkins/history` still leads there) shows it two ways:

- **Who sat where**: one row per person per seat, from check-in until someone else took the
  seat, they moved, or an admin removed them, with every IP seen in between.
- **All events**: the raw log.

Filter by seat, username (contains), IP (contains), MAC (any format, partial), time range and
event type; click a value in the table to filter on it. **Export CSV** downloads the filtered
rows (all of them, not just the 500 shown). The CSV has a UTF-8 BOM for Excel, local times plus
Unix timestamps, and values starting with `=`, `+`, `-` or `@` are prefixed with `'` so a
username can't run as a spreadsheet formula.

API: `GET /api/checkins/history` and `GET /api/checkins/history.csv`, both taking
`view=sessions|events`, `seat`, `user`, `ip`, `mac`, `event`, `since`, `until` (epoch seconds,
`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM`, server local time) and, for JSON, `limit` (default 500).
They need `CHECKIN_ADMIN_TOKEN` when it is set, and keep working after `CHECKIN_ENABLED` is
turned off, so the log can be exported after the event.

| Variable | Default | |
|---|---|---|
| `CHECKIN_HISTORY_ENABLED` | `true` | |
| `CHECKIN_HISTORY_FILE` | next to `CHECKIN_FILE` | e.g. `/app/state/checkins-history.jsonl` in Docker |
| `RECORDING_FILE` | `recording.jsonl` next to `data.json` | the whole-event recording for the replay ([replay](replay.md)) |

## Tests

```
pip install pytest
python -m pytest tests
```
