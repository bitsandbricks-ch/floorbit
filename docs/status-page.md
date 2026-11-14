# Network status page

`/status` tells attendees whether the network is fine, which areas an outage hits, and what the crew
says about it. It needs no account, so it can be linked from the event website, shown on a screen
or posted in Discord. `/status.json` has the same as JSON.

It is **off** until an admin turns on **Network status page** under **Settings > Attendee pages**
(or `STATUS_PAGE=true`). The feature can also be switched off entirely under Settings > Features.

## What the page shows

- **The state**, worked out from the status monitor every time the page loads:

  | State | When |
  | --- | --- |
  | All systems running | every switch on the floor plan is up |
  | Part of the network is down | one or more switches are down |
  | Network outage | a router or firewall is down, or half of the placed switches or more |
  | Status not available | the monitoring source isn't answering, or hasn't been asked yet |

  The crew can set the state by hand (for example **Maintenance** before planned work); it stays
  until they set it back to automatic.

- **Affected areas**: the halls, seat blocks and rows the down switches serve. Floorbit learns which
  seats a switch serves from the port descriptions it reads (the port watch, see [alerts.md](alerts.md)) and
  keeps that while the switch is down. A switch whose seats it doesn't know counts for the seat
  block nearest to it on the floor plan.
- **Updates** the crew posts, newest first (at most 50 are kept).

The page reloads itself every minute and shows times in the reader's own time zone.

## Privacy

The public page and `/status.json` show no switch names, IPs, ports, nicks or who posted what. An
admin can choose to name the switches that are down with **Switch names on the status page**
(`STATUS_SWITCH_NAMES=true`); halls, blocks and rows are shown either way.

## For the crew

**Network status** (`/network-status`, linked from Settings) shows what the public page says now,
the affected areas with the switch names, and the updates.

- Reading it needs `incidents.work`.
- Posting and removing updates and setting the state need `incidents.assign` (lead and admin).
- Every change is in the audit log (area *status page*).

## API

| Route | What |
| --- | --- |
| `GET /status`, `GET /status.json` | the public page, no account |
| `GET /api/status-page` | the crew's view: the public one plus the state set by hand and the switch names |
| `POST /api/status-page/updates` | `{"text": "...", "area": "Hall B"}` |
| `DELETE /api/status-page/updates/<id>` | removes an update |
| `PUT /api/status-page/override` | `{"state": "maintenance", "note": "..."}`, or `{"state": null}` for automatic |

The states are `operational`, `degraded`, `outage`, `maintenance` and `unknown`.
