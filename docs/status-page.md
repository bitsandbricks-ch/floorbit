# Network status page

`/status` tells attendees whether the network is fine, which areas an outage hits, and what the crew
says about it. It needs no account, so it can be linked from the event website, shown on a screen
or posted in Discord. `/status.json` has the same as JSON, and `/status.atom` has the crew's updates
as an Atom feed, so attendees can follow them in a feed reader and the event website can show them.

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
- **Back up recently**: for half an hour after a switch comes back from being down, its areas are
  listed with "The network here has been back since 14:05.", so attendees who saw the outage see
  that it is over. A switch that was simply up since Floorbit started doesn't count. The crew's
  **Network status** page lists the same areas with their switches.
- **Updates** the crew posts, newest first (at most 50 are kept).

The page updates every minute and shows times in the reader's own time zone.

## Staying current

The status page, the [stats wall](stats-wall.md), the public [schedule](schedule.md) and the
[bracket](tournament.md) update themselves in place: every minute (the bracket every 30 seconds)
the page fetches its own address again and swaps in the new content, so a big screen doesn't
flash white. A hidden browser tab waits and updates as soon as it is shown.

If the server or the network is gone for a moment, the page keeps showing the last good data with
a small note at the top, "No connection. Showing data from 14:05.", instead of a browser error
page, and picks up again by itself. Without JavaScript the page reloads every minute instead.

## Privacy

The public page and `/status.json` show no switch names, IPs, ports, nicks or who posted what. An
admin can choose to name the switches that are down with **Switch names on the status page**
(`STATUS_SWITCH_NAMES=true`); halls, blocks and rows are shown either way.

## For the crew

**Network status** (`/network-status`, linked from Settings) shows what the public page says now,
the affected areas with the switch names, and the updates.

- Reading it needs `incidents.work`.
- Posting and removing updates and setting the state need `incidents.assign` (lead and admin).
- Above the update box, **Start from** offers one button per area that is down and per area that is
  back up. A click fills in a ready text and the area. Edit it, then post. The texts use the names
  attendees see, never switch names.
- Every change is in the audit log (area *status page*).

### Planned maintenance

Under **Planned maintenance** you announce work ahead: from when until when, what attendees should
know and, optionally, where. Attendees see it under *Planned maintenance* on `/status` (and in
`/status.json` as `planned`), with the times in their own time zone. While it runs, the page shows
**Maintenance** by itself, with your text and when it ends, unless you set a state by hand, which
always wins. Once it is over it disappears and the automatic state is back. You can cancel it any
time. Up to 20 at a time, at most two weeks ahead. Like updates, it never says who planned it.

## Discord

Set **Attendee status channel webhook** (Settings > Integrations > Discord,
`DISCORD_STATUS_WEBHOOK_URL`) to a webhook in a channel attendees read, such as `#network-status`.
Every update the crew posts then goes there as well, with its state, area and a link to `/status`,
while the public status page is on. Like the page, it never says who posted, and it mentions
nobody. This is separate from the crew's alert webhook, which says much more.

## API

| Route | What |
| --- | --- |
| `GET /status`, `GET /status.json` | the public page, no account |
| `GET /status.atom` | the crew's updates as an Atom feed, no account. Its links use the Public URL (Settings > General, `PUBLIC_URL`) when it is set |
| `GET /api/status-page` | the crew's view: the public one plus the state set by hand and the switch names |
| `POST /api/status-page/updates` | `{"text": "...", "area": "Hall B"}` |
| `DELETE /api/status-page/updates/<id>` | removes an update |
| `POST /api/status-page/maintenance` | `{"start": <unix time>, "end": <unix time>, "text": "...", "area": "Hall B"}` |
| `DELETE /api/status-page/maintenance/<id>` | cancels planned maintenance |
| `PUT /api/status-page/override` | `{"state": "maintenance", "note": "..."}`, or `{"state": null}` for automatic |

The states are `operational`, `degraded`, `outage`, `maintenance` and `unknown`.
