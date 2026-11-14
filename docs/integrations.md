# Integrations

Everything lives in the `integrations/` package and is wired into `app.py` with one call:

```python
from integrations import init_integrations
init_integrations(app, load_data=load_data)
```

Each integration reads its settings through `integrations.config`, which uses environment
variables today. The settings page can take over later by calling
`integrations.config.set_provider(fn)`; anything the provider doesn't return still falls back
to the env var. `GET /api/integrations` returns `settings`, a schema of every key (label, type,
default, whether it's secret, current value with secrets masked), so a settings UI can render
the fields without hard-coding them.

## Live push updates

Browsers subscribe to `GET /api/events` (Server-Sent Events). `static/js/live.js` handles it:

| Event | When | Frontend effect |
|---|---|---|
| `hello` | on connect | applies the monitor's last known statuses |
| `switch.status` | a switch changed status | updates its dot and the hero counts |
| `data.changed` | someone added/moved/renamed/deleted a switch or seat block | reloads that list (skips your own edits, waits until you stop dragging) |
| `monitor.poll` | every status poll | none (re-dispatched only) |
| `checkin`, `checkin.removed`, `checkin.refreshed` | seat check-ins change | none (re-dispatched only) |

Every event is also dispatched on `window` as `lal:live` with `{type, data}` in `detail`, so
the reworked frontend can listen without depending on `live.js`. While connected,
`<html data-live="on">` is set (`off` otherwise) for a "live" indicator.

| Variable | Default | |
|---|---|---|
| `LIVE_UPDATES_ENABLED` | `true` | |

The event bus is in-process. That matches how the app runs (`python app.py`, threaded). If it
ever runs as several worker processes, `events.publish` is the one place to add Redis pub/sub.
Behind nginx, the stream sends `X-Accel-Buffering: no`; also set `proxy_read_timeout` above 15s.

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
poll go in one message (up to 10 embeds), so a row losing power is one message.

| Variable | Default | |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | | Channel settings → Integrations → Webhooks |
| `DISCORD_ALERTS_ENABLED` | `true` | |
| `DISCORD_NOTIFY_RECOVERY` | `true` | also post "back online" with downtime |
| `DISCORD_MENTION` | | e.g. `<@&ROLE_ID>` or `@here`, outages only |
| `DISCORD_USERNAME` | `Floorbit` | |
| `DISCORD_COOLDOWN` | `300` | seconds between outage alerts for the same switch |
| `DISCORD_HEALTH_ALERTS` | `true` | post when a service on the health wall goes red, and when it is back |
| `DISCORD_SECURITY_ALERTS` | `true` | post new high and medium security findings (where, never MACs or IPs) |
| `DISCORD_POWER_ALERTS` | `true` | post when a circuit turns red or its breaker trips, with what it feeds |
| `PUBLIC_URL` | | link in the alert |

`POST /api/integrations/discord/test` sends a test message.

## Seat → user / IP sources

`/api/seats/info`, `/api/seats/resolve` and `/api/seats/heatmap` get their seat mapping from
`integrations.seat_sources` instead of reading `seats.json` directly. Sources are merged in
the order listed in `SEAT_SOURCES`; the first one with a value for a field wins. Hand entries
from the [seat mapping](seat-mapping.md) page and plugins with `uses: [mapping]` always come
before them.

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
| `CHECKIN_TRUST_PROXY` | `false` | use `X-Forwarded-For`; only behind a proxy you control |
| `CHECKIN_VALIDATE_SEATS` | `true` | only accept seats that exist in seat blocks |
| `CHECKIN_REFRESH_INTERVAL` | `300` | seconds between MAC → IP refreshes |
| `CHECKIN_ADMIN_TOKEN` | | if set, `GET/DELETE /api/checkins` need `X-Admin-Token` |
| `CHECKIN_FILE` | `checkins.json` | |

Endpoints: `POST /api/checkin`, `GET /api/checkin/me`, `GET /api/checkins` (the
user/IP/seat/MAC table), `DELETE /api/checkins/<seat>`, `POST /api/checkins/refresh`.

### Check-in history and CSV export

Every change to the check-in table is appended to a JSON Lines log: `checkin`, `moved`
(the same machine checked in at another seat, `to_seat`), `removed`, `ip_changed` (DHCP,
`previous_ip`) and `mac_found`. `/checkins/history` shows it two ways:

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

## Tests

```
pip install pytest
python -m pytest tests
```
