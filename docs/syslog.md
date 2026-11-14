# Syslog

Floorbit can receive the logs of the event's switches, firewalls and DHCP servers by syslog, keep
them for a day and let the crew search and follow them on the **Logs** page (`/logs`). A line that
names a switch port shows the seat on that port, with a link to it on the floor plan.

Code: [`floorbit/syslog.py`](../floorbit/syslog.py) (receiving, parsing, keeping, searching),
[`floorbit/blueprints/logs.py`](../floorbit/blueprints/logs.py), [`frontend/src/pages/Logs.tsx`](../frontend/src/pages/Logs.tsx).

## Turning it on

The receiver is **off** until `SYSLOG_ENABLED` is set. It listens inside the app on udp/5514
(`SYSLOG_PORT`), not on 514, so the app doesn't need root. With Docker Compose the host's udp/514
is mapped to it (`SYSLOG_PUBLISH_PORT` to change that):

```sh
# .env
SYSLOG_ENABLED=true
SYSLOG_ALLOW=192.0.2.0/24        # the firewall and DHCP servers; switches are let in by themselves
```

Without Compose: `docker run -p 514:5514/udp ...`. For TCP as well, set `SYSLOG_TCP=true` and
publish `5514/tcp` too. TCP lines are newline-framed, which is what most senders do; octet-counted
framing isn't read.

Then point the devices at the Floorbit host. Examples:

```text
! Cisco IOS / IOS XE
logging host 192.0.2.10 transport udp port 514
logging trap informational
service timestamps log datetime msec localtime show-timezone
```

OPNsense: *System > Settings > Logging > Remote*, add a destination with transport UDP(4), the
Floorbit host and port 514, and pick the applications (firewall, DHCP).

A DHCP server on Linux (ISC dhcpd or Kea) logs through rsyslog: `*.* @192.0.2.10:514` in a file
under `/etc/rsyslog.d/`.

The feature can also be turned off as a whole under *Settings > Features* (`syslog`); then the page
and the API answer 404 and nothing is received.

## Secure by design

Logs name MACs and IPs and a syslog port is open to the network, so:

- **Off by default**, as above.
- **Allow-list.** Only senders in `SYSLOG_ALLOW` (addresses and networks, comma-separated) and,
  with `SYSLOG_ALLOW_SWITCHES` (on), the management addresses of the switches in the inventory.
  Anything else is dropped and counted ("dropped: n from senders not allowed").
- **Rate cap.** At most `SYSLOG_RATE` lines a second per sender (200); the rest is dropped and
  counted. A switch stuck in a loop can't flood the app.
- **Size caps.** A line is cut at 2 KB. At most `SYSLOG_MAX_LINES` lines are kept in memory (50,000)
  and `SYSLOG_MAX_MB` on disk (100); the oldest go first.
- **Short retention.** Lines are kept `SYSLOG_RETENTION_HOURS` (24), in one file per hour under
  `syslog/` next to `data.json` (`/app/state/syslog` in Docker), and read back after a restart.
- **Who can read them.** The page and the API need `seats.view` (admin, lead and tech by default),
  like the seat mapping.

## What Floorbit works out

For each line Floorbit keeps the text as received and adds:

| Field | Where it comes from |
| --- | --- |
| Device | The switch whose management address sent it, else the host name in the line, else the sender's address. |
| Level | The syslog severity (emergency to debug). |
| Program | The tag, for example `%LINK-3-UPDOWN` or `dhcpd`. |
| Port | The first interface the line names, `GigabitEthernet1/0/4` and `Gi1/0/4` both read as `gi1/0/4`. |
| Seat | The seat on that port of that switch, from the port descriptions the port watch reads ([alerts.md](alerts.md)). |

RFC 3164 (BSD) and RFC 5424 lines are read; a line without either is kept with level *notice*. A
line whose time is far off (a switch with a wrong clock) gets the time it arrived.

## The page

- **Search:** words that all have to be in the line (message, device, program or seat).
- **Device, Seat, Port, Level:** filters. Level shows that level and worse. Clicking a device in the
  list filters by it.
- **Live:** on by default; new lines appear every 3 seconds.
- **Older lines:** the page shows the newest 200 and pages back from there.
- The line above the list says whether the receiver is listening, how many lines are kept and how
  many were dropped.

## Floorbit's own log and the audit log

Accounts with `audit.read` (admin and lead) get two more logs on the same page, with the same
search and level filter:

- **Floorbit:** what the app itself printed, such as a plugin that couldn't reach its server or a
  file that couldn't be written. The last `APP_LOG_LINES` (2000) lines are kept in memory only; the
  container's own log has everything. The development server's request lines are left out.
- **Audit log:** who changed what ([audit.md](audit.md)), newest first, one line per change.
  Failed sign-ins show as warnings.

The Logs button in the top bar shows for them even while the syslog receiver is off.

## Log alerts

Some lines mean a seat or a switch needs a look. Floorbit knows these patterns, from Cisco IOS and
the words other vendors use:

| Pattern | Matches |
| --- | --- |
| Port shut down by the switch (err-disable) | `ERR_DISABLE`, `err-disable` |
| Port security violation | `PSECURE_VIOLATION`, `PORT_SECURITY` |
| DHCP snooping dropped packets | `DHCP_SNOOPING` |
| MAC address moving between ports | `MACFLAP`, `MAC_MOVE`, "flapping between port" |
| Loop detected | `LOOP_DETECT`, `LOOP_BACK_DETECTED`, "loop detected" |
| Storm control | `STORM_CONTROL` |
| Spanning tree topology change | `SPANTREE`, `TOPOLOGY_CHANGE`, "topology change" |

A matching line becomes a **needs-attention** item on the Problems page, with the switch, port and
seat. **A flood is one item:** more lines with the same pattern from the same device and port add to
its count ("12 lines") until it has been quiet for `LOG_ALERT_MINUTES` (15); then it clears. The
item links to the Logs page filtered to that seat or device (or to the floor plan for accounts
without `seats.view`). The item names the pattern, never the line, so it can be shown to everyone
who sees the Problems page. A new item also sends the `logs.alert` [webhook](api.md#webhooks).

**On the floor plan**, seats and switches with warnings or worse in the last 10 minutes get a cyan
underline, for accounts with `seats.view` while the receiver runs.

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `SYSLOG_ENABLED` | `false` | Turn the receiver on. |
| `SYSLOG_TCP` | `false` | Also listen on TCP, same port. |
| `SYSLOG_PORT` | `5514` | Port inside the app. |
| `SYSLOG_BIND` | `0.0.0.0` | Address to listen on. |
| `SYSLOG_ALLOW` | empty | Addresses and networks allowed to send, comma-separated. |
| `SYSLOG_ALLOW_SWITCHES` | `true` | Let the inventory's switches send without listing them. |
| `SYSLOG_RATE` | `200` | Lines a second per sender. |
| `SYSLOG_MAX_LINES` | `50000` | Lines kept in memory (at least 100). |
| `SYSLOG_MAX_MB` | `100` | Megabytes kept on disk. |
| `SYSLOG_RETENTION_HOURS` | `24` | Hours lines are kept. |
| `APP_LOG_LINES` | `2000` | Lines of Floorbit's own log kept in memory (at least 100). |
| `LOG_ALERT_MINUTES` | `15` | Minutes without a matching line before a log alert clears. |
| `SYSLOG_PUBLISH_PORT` | `514` | Docker Compose only: the host port mapped to the receiver. |

## API

`GET /api/logs` answers the newest lines first and the receiver's status. Filters: `q`, `device`,
`seat`, `port`, `severity` (the least severe level to show), `after` (only lines newer than this id,
for following along), `before` (only older, for paging) and `limit` (1 to 1000, 200 by default).
Needs `seats.view`.

`source=app` reads Floorbit's own log and `source=audit` the audit log instead; both also need
`audit.read`, and the answer's `status.sources` lists the logs the account may read.

`GET /api/logs/alerts` lists the current log alerts, and `GET /api/logs/markers` the warnings of the
last 10 minutes counted per seat and per switch (what the floor plan shows). Both need `seats.view`.

```json
{
  "lines": [{"id": 812, "ts": 1794650461.2, "severity": "err", "facility": 23,
             "device": "sw-a-01", "host": null, "program": "%LINK-3-UPDOWN",
             "message": "Interface GigabitEthernet1/0/4, changed state to down",
             "sender": "198.51.100.11", "port": "gi1/0/4", "seat": "A-4"}],
  "status": {"enabled": true, "listening": {"port": 5514, "tcp": false, "bind": "0.0.0.0"},
             "error": null, "lines": 9120, "last_id": 812, "devices": ["dhcp-01", "sw-a-01"],
             "counts": {"received": 9200, "kept": 9120, "not_allowed": 80, "rate_limited": 0},
             "retention_hours": 24, "demo": false}
}
```

## Demo

With `FLOORBIT_DEMO=1` the app makes up lines from the demo hall itself (no receiver needed): the
loose cable on seat C-9 going down and up, a MAC flapping between two ports, DHCP snooping drops,
DHCP leases, a port in err-disable, spanning tree changes and firewall blocks. The receiver stays off unless `SYSLOG_ENABLED` is set.
