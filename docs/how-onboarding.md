# Onboarding

From a fresh install to a hall that reports. The steps for people are in [install.md](install.md)
and [agent.md](agent.md#enrolling-an-agent); this page draws what happens underneath.

Code: [`floorbit/setup.py`](../floorbit/setup.py) (first-run setup),
[`floorbit/agent_link.py`](../floorbit/agent_link.py) (enrolment),
[`floorbit/blueprints/inventory.py`](../floorbit/blueprints/inventory.py) (syncs),
[`floorbit/inventory_discovery.py`](../floorbit/inventory_discovery.py) (discovery).

## The whole way

```mermaid
flowchart TD
  start["docker compose up -d<br/>(or the k3s manifest)"] --> acc{"Any account yet?"}
  acc -- "no, and AUTH_ADMIN_USER set" --> envadmin["Admin made from .env"]
  acc -- no --> code["Setup code printed to the log<br/>(new on every restart,<br/>and after 10 wrong tries)"]
  code --> first["Browser: Set up Floorbit<br/>code + first admin account"]
  envadmin --> steps
  first --> steps["Setup steps, each done or skipped:<br/>NetBox, LibreNMS, switches, theme"]
  acc -- yes --> steps
  steps --> done{"Finished or skipped<br/>to the end?"}
  done -- no --> back["The floor plan sends admins back to setup"]
  back --> steps
  done -- yes --> agent
  agent{"Agent next to Floorbit?<br/>(compose, k3s)"} -- yes --> self["Floorbit writes a key into the shared file;<br/>the agent reads it and connects as 'Local agent'"]
  agent -- "no: hosted" --> enrol["Settings > Local agents > Enrol:<br/>key shown once, only its hash kept"]
  enrol --> run["docker run ... FLOORBIT_AGENT_KEY=fba_..."]
  self --> hello
  run --> hello["Agent: hello, link, plugin settings<br/>(how-agent.md)"]
  hello --> plugins["Settings > Plugins: LibreNMS, NetBox,<br/>Telemetry, syslog, front door ..."]
  plugins --> inv["Inventory sync (Sync now, or every<br/>INVENTORY_SYNC_MINUTES)"]
  inv --> place["Place switches and seat blocks on the plan"]
  place --> tel["Turn on Telemetry for devices,<br/>groups or tags; store their logins"]
  tel --> disc["Discovery every 15 min fills empty<br/>inventory fields and ports, records drift"]
  place --> map["Seats get their ports:<br/>block patch plan, seat walk,<br/>check-in (how-seat-mapping.md)"]
```

An install that already had switches, blocks or settings before the setup existed counts as set up.

## Enrolling a hosted agent

```mermaid
sequenceDiagram
  autonumber
  actor Admin
  participant F as Floorbit
  participant A as Agent in the hall
  Admin->>F: Enrol "Spring LAN, hall 2"
  F->>F: new key fba_id_secret,<br/>keep only a hash of the secret
  F-->>Admin: key, shown once, and the docker run line
  Admin->>A: start with FLOORBIT_AGENT_KEY
  A->>F: hello with the key
  F-->>A: accepted, protocols, link
  A->>F: settings, link, report every 30 s
  F-->>Admin: Local agents page: Connected
  Note over A,F: Agent makes its own TLS key and a signing request.<br/>Floorbit's CA signs it for the names set on the agent's page
```

## A device joins the inventory

```mermaid
flowchart LR
  nb["NetBox (agent's inventory plugin)"] -- "inventory_feeds over the link" --> sync["Inventory sync:<br/>merged under each plugin's id"]
  hand["Added by hand"] --> invd[("Inventory devices")]
  sync --> invd
  invd --> feat{"Features on for the device,<br/>its group, tag or type"}
  feat -- Telemetry --> tg["Telemetry target<br/>(how-telemetry.md)"]
  feat -- "plugins per group or tag" --> ap["Agent plugins that use it"]
  mon["Monitoring source:<br/>what the device says it is"] --> disc["Discovery: fill empty fields<br/>and ports, never names or roles"]
  disc --> invd
  disc --> drift["Drift: configured vs actual,<br/>per field and port"]
```
