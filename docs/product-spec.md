# Product spec

The standing decisions behind Floorbit: what it is for, how it is built, and the rules every
change follows. Each pull request follows them. A pull request that changes one of them updates
this page in the same pull request.

Details live in the linked pages; this page says what was decided and why.

## 1. What Floorbit is

**An ops tool for the network crew of a LAN party.** It shows the event network on the floor plan:
switches and their ports, seats and which port each seat is on, live status, problems, and the
tools a tech needs to fix them. The aim is a stable platform that just works during the event.

- **Who uses it:** the crew (roles `admin`, `lead`, `tech`, `viewer`) and big screens (`kiosk`).
  Attendees only touch a few small pages: check-in, the seat help page, the network status page and
  public dashboards.
- **Any LAN can run it.** Nothing names one particular event: names, branding, hosts and hardware
  are settings or inventory.
- **Self-hosted first** (Docker Compose, Kubernetes or k3s), hosted with tenants second, with the
  same code.

### Scope

| | What | Why |
| --- | --- | --- |
| **Kept** | Floor plan editor, inventory, monitoring, incidents, check-in, seat walk-through, dashboards and big-screen walls (NOC monitors), seat help page, crew schedule, crew Discord bot | The crew's daily work |
| **Shrunk** | Speedtest (limited, per seat), event replay (whole-event recording only), Marketplace (official signed plugins only), network status page (no maintenance, feeds or switch names) | Useful, but not worth their old size |
| **Cut** | Tournament brackets, runbooks, find-your-seat, public agenda, attendee Discord use, build planner, teardown, gear lending, inventory of items (gear), AI or LLM features | Attendee or club features outside the ops job |
| **Not now** | Seatbit integration; the Lock and Load backend (it is reworked in 2027) | Later, if at all |

Cut features are not re-added. "Inventory" means network devices and what belongs to them (cables,
power, racks, VLANs), never gear.

## 2. Architecture

### One code path

There are no hosted and self-hosted variants of the same thing. Where two ways exist, one goes.

| Rule | What it means |
| --- | --- |
| **Tenants, with a default tenant** | Platform > tenant > event. A self-hosted install is the `default` tenant; hosted adds more. One live event per tenant, one process per tenant. Platform admins (flagged admins of the default tenant) add tenants and set their admins; a tenant's admins are its own Admin accounts and decide whether platform admins may visit. The UI says "tenant" (German "Mandant"), never "club". See [tenancy.md](tenancy.md). |
| **Agent-only LAN access** | The local agent is the only way Floorbit reaches the event network, even when app and agent run side by side. No direct path, no request-IP shortcut. See [agent.md](agent.md). |
| **One database layer** | SQLite by default, Postgres for bigger or hosted installs, same migrations. No JSON-file backend. See [database.md](database.md). |
| **Valkey for cache and live only** | Durable data goes to the database; Valkey holds cache, live updates and pub/sub (env stays `REDIS_*`). |
| **Agent plugins configured from the app** | The agent reads no plugin settings from its own env; the hosted side hands them over. |
| **Agent settings from the app, env wins** | An agent's own settings are set on its page in Floorbit; a value its own env sets wins and the page shows each value's source. Its safety limits (actions, plugin updates, networks it may reach) are env-only, so a stolen login can't widen them. Floorbit rolls keys (the agent fetches them) and signs agent certificates with its own CA; private keys stay on the agent. |

### Building blocks

- **Server:** Flask JSON API (`floorbit/`, one blueprint per area). **Frontend:** React, TypeScript,
  Vite, TanStack Query and Mantine (Hubra's setup). **One Docker image.**
- **Local agent:** its own repository (bitsandbricks-ch/floorbit-agent). One outgoing connection
  (WebSocket over TLS, HTTPS long-poll fallback); nothing on the event network is reachable from
  outside. One agent per hall is the tested limit; agents fail over with VRRP.
- **Telemetry:** Telegraf on the agent; VictoriaMetrics and VictoriaLogs when configured, lite
  rollups in the database otherwise. LibreNMS is an optional monitoring provider.
- **Seat to port:** the durable key of a seat is **switch + port**. IP and MAC are looked up
  (IP to MAC from core ARP, MAC to edge port from access FDB) and never key durable data.
- **Survives outages:** the app keeps serving reads when the database is down, shows a banner and
  never saves state that started from nothing. See [database.md](database.md).
- **Running it:** one replica by default; more replicas need Postgres and Valkey. Deploys use pinned
  image tags (`ghcr.io/bitsandbricks-ch/floorbit:<sha>`).
- **Settings:** a value saved in the UI wins over the env var, which wins over the default. Only
  startup values stay env-only (database URL, Valkey, secret key, vault keys, first admin, listener
  ports, hosted-server limits). See [integrations.md](integrations.md#where-a-setting-lives).

## 3. Modularity

- **Every integration is a plugin.** NetBox, LibreNMS, telemetry, syslog and flow relays, health
  checks and the demo are built in; optional integrations (LAN cache, Shelly, Home Assistant, more
  later) are Marketplace plugins in their own `floorbit-plugin-*` repositories. Everything the agent
  does on the event network is an agent plugin, and plugins can add to the agent's own health.
- **The core asks, plugins answer.** The core talks to the inventory and
  `floorbit.sources.monitoring()`, never to a vendor API.
- **What a plugin may ship** is fixed in [plugin-spec.md](plugin-spec.md): settings, inspector panels,
  plan layers, pages, widgets, documents with migrations, translations, an icon. Never browser code,
  native code, extra packages, own routes, SQL tables or new roles. Screens are data Floorbit draws.
- **Marketplace:** official plugins only, signed, with install, update, rollback and withdrawn
  versions. Agents only run signed bundles, so a stolen hosted login cannot run code in the hall.
  See [marketplace.md](marketplace.md).
- **Widgets first.** Anything dashboard-like is built from widgets (`frontend/src/widgets/`), so it
  also works on custom dashboards and big screens. Overview pages (Overview, Health, Traffic, Power)
  are ready-made dashboards; read-only pages became widgets. Pages with tools stay pages.
  See [dashboards.md](dashboards.md).
- **Shared components, no look-alikes.** Before building a card, table, form field or dialog, use
  what exists: `EntitySelect`, `ConfirmButton`/`ConfirmIcon`, `DateTimeInput`, `PageTabs`,
  `SidePanel`, `StatCard`, the telemetry components. New visual blocks become shared components or
  widgets.
- **Where code goes:** a new API area is a blueprint, a new page is a React page with English and
  German texts, a new editor feature is a file in `frontend/src/pages/plan/edit/`, new on-plan data is
  a layer. Prefer a new file per feature over growing a shared one.

## 4. UI and UX

### Identity

- **Its own product.** The page structure borrows from Labdex; the look is Floorbit's own.
- **Dark first;** light and system theme per person. Colours only through brand tokens (`--ui-*`,
  `--brand-*`). Bit Green is the accent, Trace Cyan is only for selection and seat-to-port traces,
  status colours (up, down, warn, unknown, disabled) are fixed and never themable.
- **Type:** Geist for text and titles, Geist Mono only for numbers. Square status "bits" and the
  floor-tile grid are the recurring motifs.
- **Customising** is accent and highlight colour, logos, square mark and name. No theme presets.
  The Discord bot uses the same name, mark and accent. See [themes.md](themes.md).

### Structure

- **Shell:** event picker at the top of the sidebar, grouped sidebar, top bar with breadcrumbs,
  Go to (`Ctrl K`) and notifications, a status line. Pinned favourites per person, including
  dashboards. The tenant switcher shows only with two or more tenants.
- **Sidebar groups:** Overview and Floor plan · **Live** (Incidents, Dashboards) · **Inventory**
  (Devices, Cables, Power, Racks and patch panels, VLANs and IP ranges) · **Monitoring** (Health,
  Network, Services, Traffic, Logs) · **Seats** (Seats and check-in, IP and MAC) · **Event** ·
  **Floorbit** at the bottom (Agents, Plugins, Settings).
- **Every feature has its own main page,** and every device has a detail page with tabs for what it
  does (ports, telemetry, configs, ...). Few pages, more tabs: merge before adding.
- **Page types:**

  | Type | Use for | Examples |
  | --- | --- | --- |
  | Table | Many similar rows to search and sort | Devices, Seats, Logs, IP and MAC |
  | Cards | A handful of things with state | Incidents board, Game servers, Firewalls, Agents, Plugins |
  | Dashboard | Read-only overview, built from widgets | Overview, Health, Traffic, Power |
  | Workspace | Full-screen tool | Floor plan, Topology, Terminal, Replay |
  | Detail page | One thing, with tabs | A device, an agent, a seat |

- **Side panel or detail page:** a click opens a side panel to peek and act quickly; anything
  bigger opens the detail page. The panel links there. The inventory has no side panel: devices,
  groups, tags and entries each open their own page.
- **Floor plan:** one full-screen map editor, not separate modes. Live status is always on, edit
  tools follow the role, the plan is an infinite grid, layers stack with presets and each layer has
  its own legend, filters are chips in the top bar, one docked panel on the right.

### Rules for every page

- **No free text for known data.** Switches, ports, seats, blocks, halls, devices, agents, users,
  teams and VLANs are picked from a searchable list (`EntitySelect`). No native `<select>`.
- **Controls look the same everywhere;** pages never restyle them. Menu text is 14px like page text.
- **Deletes ask first** (`ConfirmButton`), never `window.confirm`, `alert` or `prompt`.
- **Languages:** English and Swiss German everywhere (pages, server errors, Discord, logs); standard
  German is derived. No "ß". Terms: Sitzblock, Störung, Hallenplan, Mandant.
- **Dates and times:** day-first (19.11.2026) and 24-hour in every language, through
  `frontend/src/lib/time.ts`; date fields use `DateTimeInput`.
- **Phone and big screen:** every page works on a phone (wide tables stack into cards, panels become
  bottom drawers) and readable on a wall (kiosk dashboards, seat labels that fit the zoom).

## 5. Privacy and security

- **Aggregates only** leave the event network for NetFlow, DNS and Wi-Fi. Stats about people need at
  least 5 seats; per seat only volume and protocol mix. Raw data is kept about 7 days.
- **ARP and MAC history is stored** per port and seat (7 days), visible with `seats.view` only.
- **Device secrets** (SSH logins, RCON passwords, secret settings) are encrypted at rest, write-only
  in the UI, decrypted per call, limited by role and written to the audit log.
- **Roles and audit:** every change and sign-in is audited; check-in records are never public.
- **Agents dial out only;** plugins and agent bundles are signed; keys and signing are the
  maintainer's.
- **No personal data** in code, fixtures, screenshots or logs: use `example.com` and `192.0.2.x`.

## 6. How we build it

- **Floorbit is a dev product,** not live anywhere. No redirects for moved pages, no
  backward-compatibility shims, no migrations for removed features.
- **One topic per pull request, based on `master`.** No stacked branches. Threads that touch the same
  files go one after the other.
- **Draft first,** fill in the template, ready only when the work is done and CI is green. Never skip
  or weaken a check. The maintainer (Mike) merges and releases.
- **Screenshots on every pull request,** UI change or not; English and Swiss German where text
  changed, phone where layout changed.
- **Changelog:** one `changelog.d/<topic>.md` fragment when people notice the change. `VERSION` and
  release headings are `mason bump`'s.
- **Tests use fakes,** never a real NetBox, LibreNMS, Valkey, device or agent.
- **Ask, don't guess** about facts. For design choices, pick a sensible default, say so in the pull
  request and keep going.
- The coding rules are in [AGENTS.md](https://github.com/bitsandbricks-ch/floorbit/blob/master/AGENTS.md).
