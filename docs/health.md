# Service health wall

One screen for the services a LAN lives on: DHCP (leases left per scope), DNS, the LAN cache (hit
rate, traffic saved), game servers and the internet uplink, each **green** (up), **amber**
(degraded), **red** (down) or grey (unknown). It is the **Service health** widget ([widget gallery](dashboards.md#the-widget-gallery)) and the
ready-made **Service health** dashboard (`/dashboards/health`). On a crew screen, every check is a
row on the [Services](services.md) page, with its numbers, forecast and mute in the row's panel (the
separate Service health page went into it, issue #1337).
Code: [`floorbit/health.py`](../floorbit/health.py) and
[`floorbit/blueprints/health.py`](../floorbit/blueprints/health.py).

## On a big screen

Open `/dashboards/health` on the screen, signed in with a `kiosk` account. Small, the widget shows
only what is down or degraded (or "all fine"); big it shows every check and **Check now**. It
refreshes on its own and as soon as a service changes colour.

## Where the checks come from

Floorbit checks nothing itself, except the [game servers](game-servers.md), the internet lines,
resolvers, sites and own checks (ping, TCP, UDP, HTTP(S)) on the [Services](services.md) page, the LAN cache Floorbit reads and the [firewalls](firewalls.md), each set
up on its own page.
Every other service on the wall comes from a plugin with `uses: [health]` (see [plugins.md](plugins.md)):

- **HTTP check** (built in) puts each of its web services on the wall: red when it doesn't answer
  or answers with an error, amber when it takes longer than 2 seconds.
- **Demo data** fills the wall with made-up services (see [demo.md](demo.md)); one game server goes
  down two minutes in every five, so alerts can be tried.
- Your own plugin for your DHCP server, resolvers, cache or game servers.

A plugin's `health_checks()` returns a list:

```python
[{"id": "dhcp-players", "name": "DHCP players", "kind": "dhcp", "status": "warn",
  "summary": "38 leases left", "link": "/dashboard",
  "metrics": [{"label": "Leases left", "value": 38, "unit": "", "tone": "warn"}]}]
```

| Key | |
| --- | --- |
| `id` | unique within the plugin (Floorbit puts the plugin id in front) |
| `name` | what the tile says, up to 60 characters |
| `kind` | `dhcp`, `dns`, `cache`, `game`, `uplink`, `firewall`, `web` or `other`: the wall groups by it |
| `status` | `up`, `warn`, `down` or `unknown` (anything else is `unknown`) |
| `summary` | one line, up to 120 characters |
| `metrics` | up to 6 `{label, value, unit, tone}`; `tone` is `ok`, `warn`, `err` or empty |
| `link` | optional, a path on this site |
| `capacity` | optional, `{"used": 96, "total": 120}`: how much of a pool is used (a DHCP scope), for the forecast below |

Like widgets, checks are data: text is shown as text and links only go to this site. A plugin that
fails shows as one grey tile; the error is in its log under **Settings › Plugins**. The plugin
decides what amber and red mean, since a "low" lease count depends on the scope.

### When a pool runs full

A check with `capacity` gets a forecast (issue #1061). The wall keeps the counts for an hour, works
out how fast they grew over the last 15 minutes, and says "Full in about 25 minutes at 2 a minute"
on the tile. The doors-open rush (phones, consoles, second PCs) can fill a DHCP scope in minutes, so
this warns while there are still addresses left:

- A check the plugin calls `up` turns amber when its pool is forecast full within an hour, or is
  85 % used. Problems then reads "DHCP players: full in about 25 min", and the usual alerts go out.
- The forecast needs 5 minutes of counts first, so a restart doesn't warn anybody. When a scope's
  size changes, it starts over.
- The plugin's own amber and red still win: the forecast only ever adds a warning.

Write `summary` and metric labels in English. On a German page the wall shows the German text from
`floorbit/locales/de-CH/` when there is one (Floorbit's own checks and the demo have them), and
the plugin's own words otherwise.

## Polling and alerts

A background thread asks every health plugin every **Check interval** seconds (30 by default,
**Settings › Service health wall**, or `HEALTH_INTERVAL`). A new colour counts once it was seen
**Checks to confirm a change** times in a row (2, `HEALTH_CONFIRM`), so one slow answer pages
nobody. The first round after a start only records what is there, like the switch status monitor.

A confirmed change publishes `health.changed` to open browsers and runs plugin hooks on
`health.status`. With a Discord webhook set (see [integrations.md](integrations.md)), a service going
**red** posts a message (with **Mention on outage** in front), and with **Notify on recovery** it
posts again when it is back. Amber posts nothing. The per-switch cooldown applies per service too.
Turn health messages off with **Health wall alerts** (`DISCORD_HEALTH_ALERTS=0`).

## Who can do what

| | Needs |
| --- | --- |
| See the wall (`GET /api/health`, the Services page) | `floorplan.view` (every role, kiosk included) |
| **Check now** (`POST /api/health/check`) | `plugins.run`: it sends the plugins' requests out right away |

On a hosted Floorbit, the health plugins can run on the [local agent](agent.md#health-checks-through-the-agent) instead, so services inside the hall are checked from inside the hall.
