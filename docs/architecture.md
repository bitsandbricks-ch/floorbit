# Architecture

How Floorbit is put together, and where a change goes. The aim is that two pull requests about
different features touch different files.

## Server (`floorbit/`)

`app.py` only calls `create_app()` from `floorbit/__init__.py`, which wires the parts in this order:

1. **`auth/`**: sign-in, roles and accounts. Registered first, so its request guard runs before
   anything else.
2. **`floorbit/settings.py`** (the `/settings` page and its store) and **`floorbit/runtime.py`**:
   the values the app runs with right now (`rt`), refreshed whenever settings are saved.
3. **`floorbit/cache.py`**: the Redis connection and the cache of LibreNMS answers.
   **`floorbit/theme.py`**: the preset and colours every page renders with, `?theme=` per
   screen and the event logo at `/brand/logo` (see [themes.md](themes.md)).
   **`floorbit/audit.py`**: appends every successful change and sign-in to the audit log.
4. **`floorbit/blueprints/`**: one blueprint per area, listed in `blueprints/__init__.py`:

   | Module | Routes |
   | --- | --- |
   | `pages.py` | `/`, `/kiosk` |
   | `config.py` | `/api/config` |
   | `switches.py` | `/api/switches...`: the floor plan's view of the inventory (list, sync, add, move, rename, remove) |
   | `inventory.py` | `/inventory`, `/api/inventory...` (see [inventory.md](inventory.md)) |
   | `seat_blocks.py` | `/api/seats`, `/api/seat-blocks...` |
   | `network.py` | switch status, `/api/resolve/<ip>`, `/api/seats/info`, `/resolve`, `/heatmap` |
   | `backup.py` | `/api/settings/backup` (download, restore; see [backup.md](backup.md)) |
   | `audit.py` | `/settings/audit`, `/api/settings/audit`, `.csv` (see [audit.md](audit.md)) |
   | `plugins.py` | `/settings/plugins`, `/dashboard`, `/api/plugins/...` (see [plugins.md](plugins.md)) |
   | `cache.py` | `/api/cache/...` |

5. **`integrations/`**: live updates (SSE), the status monitor, Discord alerts, seat sources and
   the check-in page. See [integrations.md](integrations.md).

`floorbit/store.py` reads and writes `data.json`, which holds the floor plan, settings and accounts.

### Inventory and data sources

`floorbit/inventory.py` owns the list of devices (see [inventory.md](inventory.md)); plugins with
`uses: [inventory]`, such as the built-in NetBox plugin, feed it, and `blueprints/inventory.py`
runs the syncs. The floor plan's `/api/switches` works on the same list.

Live data comes through `floorbit/sources/`: `sources.monitoring()` answers from the monitoring
plugin that is on (the built-in LibreNMS plugin, `floorbit/builtin_plugins/librenms/`) with
`devices()`, `device_details(hostname)`, `resolve_ip(ip)`, `port_stats(hostname, port)`,
`mac_for_ip(ip)` and `ip_for_mac(mac)`. The blueprints, the status monitor and the check-in page all
ask it; nothing else talks to LibreNMS. With no monitoring plugin on, everything reads as unknown.
`sources.use(fake)` swaps the source (tests, later the local agent) and `sources.use(None)` goes back.

## Browser

The browser side is moving to React one page at a time (issue #46).

### React app (`frontend/`)

React 19, TypeScript, Mantine and TanStack Query, built with Vite, set up like Hubra's
`app/frontend`. `npm run build` writes it to `static/app/` (not committed; the Docker image builds
it). Flask stays the JSON API and serves the pages: a route that moved to React returns
`spa.render(title)` from `floorbit/spa.py`, which renders `templates/spa.html` with the theme head
and the asset tags from Vite's manifest. So the preset, colours and light/dark from the server
apply before React paints, and sign-in and roles are checked by Flask as for any page.

- `src/pages/`: one file per page, loaded lazily. Routes are in `src/App.tsx`.
- `src/api/`: the fetch client (same origin, cookie session; a 401 goes to the sign-in page),
  the response types and the TanStack Query hooks. Query keys live in `src/api/keys.ts`.
- `src/theme.ts`: Mantine on top of the design tokens, as CSS variables, so themes need no rebuild.
- `src/i18n/`: texts per feature, in English (`en`) and Swiss German (`de-CH`); a test checks both
  have the same keys.
- `src/widgets/`: draws plugin widgets. Everything a plugin returns is shown as text; ESLint
  refuses `dangerouslySetInnerHTML`.

Moved so far: `/dashboard`, `/settings/plugins`, `/inventory`. Without a build these answer 503 with the steps
to make one.

### Older pages (`static/`)

Plain JavaScript and CSS, no build step.

- The editor (`templates/index.html`) is split by feature in `static/js/editor/`. The files are
  classic scripts sharing one global scope, loaded in a fixed order; see
  [static/js/editor/README.md](../static/js/editor/README.md) for the order and the two rules
  that keep it working.
- Other pages have their own script and stylesheet (`settings.js`, `users.js`, `kiosk.js`, ...).
- `templates/_attribution.html` and `static/css/attribution.css` are the "Buy me a coffee" and
  "Powered by bitsandbricks.ch" links every page includes.

## Changelog (`changelog.d/`)

One fragment per pull request; `scripts/changelog.py collect` merges them at release. See
[changelog.d/README.md](../changelog.d/README.md).
