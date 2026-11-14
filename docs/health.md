# Service health wall

One screen for the services a LAN lives on: DHCP (leases left per scope), DNS, the LAN cache (hit
rate, traffic saved), game servers and the internet uplink, each **green** (up), **amber**
(degraded), **red** (down) or grey (unknown). Open it at **Health** in the top bar (`/health`).
Code: [`floorbit/health.py`](../floorbit/health.py) and
[`floorbit/blueprints/health.py`](../floorbit/blueprints/health.py).

## On a big screen

**Big screen** (`/health?screen=1`) drops the header and makes the tiles readable from across the
hall. The wall gets the kiosk theme unless the screen picks another one with `?theme=` (see
[themes.md](themes.md)), so a kiosk account works as it does for `/kiosk`: sign the screen in
with a `kiosk` account and open `/health?screen=1`. The page refreshes on its own and as soon as
a service changes colour.

## Where the checks come from

Floorbit checks nothing itself. Every service on the wall comes from a plugin with
`uses: [health]` (see [plugins.md](plugins.md)):

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
| `kind` | `dhcp`, `dns`, `cache`, `game`, `uplink`, `web` or `other`: the wall groups by it |
| `status` | `up`, `warn`, `down` or `unknown` (anything else is `unknown`) |
| `summary` | one line, up to 120 characters |
| `metrics` | up to 6 `{label, value, unit, tone}`; `tone` is `ok`, `warn`, `err` or empty |
| `link` | optional, a path on this site |

Like widgets, checks are data: text is shown as text and links only go to this site. A plugin that
fails shows as one grey tile; the error is in its log under **Settings › Plugins**. The plugin
decides what amber and red mean, since a "low" lease count depends on the scope.

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
| See the wall (`GET /health`, `GET /api/health`) | `floorplan.view` (every role, kiosk included) |
| **Check now** (`POST /api/health/check`) | `plugins.run`: it sends the plugins' requests out right away |
