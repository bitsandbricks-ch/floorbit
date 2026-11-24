# LibreNMS alerts

When LibreNMS watches the event network, it can tell Floorbit about an alert the moment it fires,
instead of Floorbit finding out at its next poll. LibreNMS sits on the event network and the
[local agent](agent.md) is the only way in, so LibreNMS sends each alert to the agent, and the agent
passes it on (issue #951). Code: [`floorbit/librenms_alerts.py`](../floorbit/librenms_alerts.py),
the built-in plugin [`librenms-alerts`](../floorbit/builtin_plugins/librenms-alerts/) and
[`floorbit/blueprints/librenms_alerts.py`](../floorbit/blueprints/librenms_alerts.py).

## What it does

- Every alert shows on the [Problems page](alerts.md) right away, with LibreNMS's title, the device
  and the ports it names. A critical alert is **down** (red), anything else needs a look (amber).
  Floorbit takes every alert, also from rules it knows nothing about.
- Every alert wakes the status monitor, so a switch LibreNMS saw go down shows offline on the plan
  within seconds.
- **Open** goes to the device on the floor plan when it is in the inventory under the same name
  (LibreNMS's `sysName`, else its `hostname`).
- A recovery (state 0) clears the alert. "Worse" and "better" replace it: a port alert lists all the
  ports still down each time, so a port missing from a later update is fixed.
- Acknowledged in LibreNMS: it stays on the list, as amber, with "(acknowledged in LibreNMS)".
- If a recovery got lost, Floorbit notices by itself: while alerts are open, the status monitor reads
  LibreNMS's list of open alerts (`GET /api/v0/alerts`) through the agent at most every 5 minutes,
  and clears an alert whose id LibreNMS no longer lists. An alert younger than 3 minutes is left
  alone (LibreNMS may not list it yet), and a list that can't be read clears nothing. People with
  `incidents.work` can still clear one at once with **Clear** on the Problems page.

Each alert is kept under its agent, its device and LibreNMS's alert id, which stays the same from
the alert to its recovery. An update older than the one Floorbit has (the agent can send queued
alerts late) changes nothing. Alerts hold device and port names only, never people.

## Setting it up

The plugin is on by default. Each agent listens on port **9530** (the plugin's setting on
**Settings > Plugins > LibreNMS alerts**; 0 turns it off), with HTTPS when the agent has a
certificate. That page shows what to paste into LibreNMS, under **Alerts > Alert transports**, new
transport of type **API**:

| Field | Value |
| --- | --- |
| API method | `POST` |
| API URL | the URL shown for your agent, e.g. `https://agent.example.com:9530/librenms` |
| Headers | `Content-Type=application/json` |
| Auth: Bearer token | the token shown on the page |
| Body | the body template shown on the page |

Turn off "Verify SSL" in the transport unless LibreNMS trusts the agent's certificate. Give the
alert rules this transport, with recoveries on.

The token is made on first use; nobody has to type one into Floorbit. **New token** replaces it
(every agent gets the new one with its next config) and LibreNMS needs the new one pasted.
Looking at the token and making a new one need `settings.manage`, and both go to the audit log.

The URL names the agent's address in the hall once a browser has reached the agent's front door
there; until then it says `<agent address>` and you fill in the agent's address.

TODO: the body template is written from the LibreNMS docs and has not been tried on a real LibreNMS
yet. Check it with the transport's test button before the event, and tell us what to change.

## Not in this version

- Flags on the port, the plan and the seats behind it; health values (temperature, optics, PoE),
  routing peers and LibreNMS service checks in their own places (issue #951).
- A ready-made rule set to paste.
