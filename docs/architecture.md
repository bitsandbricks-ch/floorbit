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
4. **`floorbit/blueprints/`**: one blueprint per area, listed in `blueprints/__init__.py`:

   | Module | Routes |
   | --- | --- |
   | `pages.py` | `/`, `/kiosk` |
   | `config.py` | `/api/config` |
   | `switches.py` | `/api/switches...` (list, NetBox sync, add, move, rename, delete) |
   | `seat_blocks.py` | `/api/seats`, `/api/seat-blocks...` |
   | `network.py` | switch status, `/api/resolve/<ip>`, `/api/seats/info`, `/resolve`, `/heatmap` |
   | `cache.py` | `/api/cache/...` |

5. **`integrations/`**: live updates (SSE), the status monitor, Discord alerts, seat sources and
   the check-in page. See [integrations.md](integrations.md).

`floorbit/store.py` reads and writes `data.json`, which holds the floor plan, settings and accounts.

### Data sources (`floorbit/sources/`)

Blueprints never call the NetBox or LibreNMS API modules themselves. They ask:

- `sources.inventory()`: which switches exist (`fetch_devices()`); NetBox today.
- `sources.monitoring()`: `device_details(hostname)`, `resolve_ip(ip)`, `port_stats(hostname, port)`;
  LibreNMS today.

`sources.use(inventory=..., monitoring=...)` swaps either one. That keeps a hosted version open
(issue #2), where a small agent at the event feeds the data in instead of direct API calls, and it
keeps other NMSs possible. Not yet behind it: the status monitor and the check-in MAC lookup in
`integrations/` still call LibreNMS themselves; moving them is a follow-up.

## Browser (`static/`)

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
