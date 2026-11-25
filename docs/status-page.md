# Network status page

`/status` tells attendees whether the network is fine, which areas an outage hits, and what the crew
says about it. It needs no account, so it can be linked from the event website, shown on a screen
or posted in Discord. `/status.json` has the same as JSON. `/hall`, where the old attendee view
was, leads here.

It is **off** until an admin turns on **Network status page** under **Settings > Attendee pages**
(or `STATUS_PAGE=true`). The feature can also be switched off entirely under Settings > Features.

## What the page shows

- **The state**, worked out every time the page loads from what players notice: the status monitor's
  switches and the network checks of the [service health wall](health.md) (firewalls, internet lines,
  DNS, DHCP). Game servers, websites and the LAN cache don't count: they aren't "the network".

  | State | When |
  | --- | --- |
  | All systems running | every switch on the floor plan is up, and no firewall, internet line, DNS or DHCP check is down |
  | Part of the network is down | one or more switches are down, a firewall is down (its ranges failed over), one internet line is down, or DNS or DHCP is down |
  | Network outage | a router or firewall in the inventory is down, half of the placed switches or more, every internet line, or a seat range left without a firewall |
  | Status not available | the monitoring source isn't answering, or hasn't been asked yet |

  Under the state, one plain line per cause says what players notice ("One internet line is down:
  the internet may be slower."), never a device name.

  The crew can set the state by hand (for example **Maintenance** during planned work, with an
  update saying what and until when); it stays until they set it back to automatic.

- **Affected areas**: the halls, seat blocks and rows the down switches serve, and the seats whose
  range moved to another firewall (or has none left). Floorbit learns which
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

The status page and the [stats wall](stats-wall.md) update
themselves in place: every minute the page fetches its own address again and swaps in the new content, so a big screen doesn't
flash white. A hidden browser tab waits and updates as soon as it is shown.

If the server or the network is gone for a moment, the page keeps showing the last good data with
a small note at the top, "No connection. Showing data from 14:05.", instead of a browser error
page, and picks up again by itself. Without JavaScript the page reloads every minute instead.

## Privacy

The public page and `/status.json` show no switch names, IPs, ports, nicks or who posted what: only
halls, blocks and rows. The crew's own page names the switches.

## For the crew

**Network status** (`/network-status`, linked from Settings) shows what the public page says now,
the affected areas with the switch names, and the updates.

- Reading it needs `incidents.work`.
- Posting and removing updates and setting the state need `incidents.assign` (lead and admin).
- Above the update box, **Start from** offers one button per area that is down and per area that is
  back up. A click fills in a ready text and the area. Edit it, then post. The texts use the names
  attendees see, never switch names.
- **Area** lists the halls and seat blocks to pick from; anything else (a service, the catering) can
  still be typed in.
- **Set the state** starts on the state the page shows now, so pinning it takes one click.
- Every change is in the audit log (area *status page*).

## Discord

The crew posts updates from Discord too, with `/statusupdate` ([crew-discord.md](crew-discord.md#slash-commands)).
Floorbit doesn't post them to a channel attendees read: attendees read the network status on `/status`.

## API

| Route | What |
| --- | --- |
| `GET /status`, `GET /status.json` | the public page, no account |
| `GET /hall` | leads to `/status` (where the attendee view was) |
| `GET /api/status-page` | the crew's view: the public one plus the state set by hand and the switch names |
| `POST /api/status-page/updates` | `{"text": "...", "area": "Hall B"}` |
| `DELETE /api/status-page/updates/<id>` | removes an update |
| `PUT /api/status-page/override` | `{"state": "maintenance", "note": "..."}`, or `{"state": null}` for automatic |

The states are `operational`, `degraded`, `outage`, `maintenance` and `unknown`.
