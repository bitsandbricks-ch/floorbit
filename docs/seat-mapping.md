# Seat mapping

The seat mapping says which IP, MAC and nick belong to each seat. The floor plan uses it to show
who sits where, to find a seat's switch port, and for the heatmap. Floorbit owns the mapping: it
works with no plugin at all, typed in by hand on the **Seat mapping** page (`/seat-mapping`),
and plugins, the check-in page and `seats.json` can fill it too.

## Where each field comes from

Floorbit asks every seat source and merges what they send, field by field. The first source
with a value for a field wins:

1. **Hand entries** from the Seat mapping page. Always first, so what you type wins.
2. **Plugins** with `uses: [mapping]` that are turned on.
3. The sources in `SEAT_SOURCES` (`json` for `seats.json`, `checkin`, `http`), in that order.
   See [integrations](integrations.md#seat--user--ip-sources).

A field you leave empty on a hand entry is filled from the other sources. The page shows which
source gave each field, so you can see why a seat has the IP it has. Removing a hand entry
brings the other sources' values back.

## Import and export

**Export CSV** downloads the hand entries (`seat,ip,mac,nick,note`). **Import CSV** reads the
same columns. Every row is checked before anything is written: one bad row stops the whole
import and the page lists the lines and what is wrong with them. Import adds and changes seats;
tick *Replace* to also drop hand entries the file doesn't have. MACs can be written any common
way (`AA-BB-CC-DD-EE-FF`, `aabb.ccdd.eeff`) and are stored as `aa:bb:cc:dd:ee:ff`. Cells that a
spreadsheet would run as a formula are escaped in the export.

## Privacy

Nicks, IPs and MACs are personal data:

- The page and its API are for editors and admins only, even when `AUTH_PUBLIC_READ` is on.
- The audit log names the seat and which fields changed, never the values.
- Backups leave the seat mapping out. Keep a CSV export instead if you need one.
  <!-- TODO ask Mike: include the seat mapping in backups (opt in)? -->

## Writing a plugin that feeds it

Add `mapping` to `uses:` and define `seat_mapping()` returning
`{"A-1": {"ip": "192.0.2.11", "mac": "02:00:00:00:00:11", "nick": "player-one"}}`. Each field is
optional. Bad entries (a seat label that isn't one, an IP or MAC that doesn't parse) are dropped
and counted, never stored. A plugin that fails shows its error on the Seat mapping page and the
other sources still work.

## API

| Request | What it does |
| --- | --- |
| `GET /api/seat-map` | Every seat with its merged ip, mac and nick, which source gave each field, the hand entry, and the sources with their last errors |
| `PUT /api/seat-map/<seat>` | Set the seat's hand entry (`ip`, `mac`, `nick`, `note`); empty fields are dropped |
| `DELETE /api/seat-map/<seat>` | Remove the hand entry |
| `GET /api/seat-map.csv` | The hand entries as CSV |
| `POST /api/seat-map/import` | `{"csv": "...", "replace": false, "dry_run": true}`; a dry run only checks |

## Finding a player

The search box on the floor plan (press `/`) finds switches, seats and nicks, and for accounts with
`seats.view` also IPs and MACs (issue #14). A MAC can be written any common way (`02:00:..`,
`02-00-..`, `0200.0000.0009`).

A full IP or MAC is also looked up on the network (`GET /api/seats/find?q=`):

- when no seat source knows it, the monitoring source's ARP table turns the IP into a MAC (or back)
  and that finds the seat;
- the switch port it is plugged into is resolved, and shows under **On the network** even when no
  seat is known for it.

Picking a result jumps to the seat, opens it, and the switch it hangs on lights up for a few
seconds. Nicks, IPs and MACs never reach roles without `seats.view`; they still find switches and
seat numbers.

## Checking in from a PC

A PC has no camera, so nobody has to scan the QR code. With check-in on (`CHECKIN_ENABLED`), every
seat card on the printed sheet (Incidents, then Seat QR codes) also carries:

- the **short address** to type, `CHECKIN_ADDRESS` (for example `checkin.example.com`). Point that
  name at Floorbit in the event DNS; opening it lands on `/checkin`. It also shows on the sign-in page.
- the seat's **PIN**: five characters, unique per seat, without look-alikes (no 0/O, 1/I/L, 5/S, 8/B).
  PINs are made the first time the sheet is opened and kept, so a reprint gives the same cards.

The attendee types the PIN and their nick, never the seat: the PIN names it. Floorbit then finds
the switch port the PC is on. ARP only lives on the core switches, so it takes two steps: the
request's IP gives the MAC from the core's ARP table, and that MAC is looked up in the MAC tables
(FDB) of every switch. Every switch between the core and the seat learns the MAC too, on its uplink,
so the port with the fewest MACs wins; ports named in "Ignored port names" and ports whose
description matches the uplink pattern (`STATS_UPLINK_PATTERN`) are skipped.

What Floorbit keeps is the pair **seat to switch port** (`seat_ports.json` next to `checkins.json`).
The IP was only the way there. From then on the seat counts as patched to that port wherever the
plan asks (port problems, syslog lines, the seat view, "who is on this port"), and the seat shows
the MAC and IP that are on that port now, from the MAC and ARP tables. A cable drawn in the patch
plan always wins over a learned port.

The Problems page lists check-ins that disagree, as **Seat port** entries: two seats checked in on
the same port, a port the patch plan gives to another seat, or a seat taken over by another nick.
They name the seat and port, never the nick.

The phone page can still take a typed seat number (the QR code case). That records the check-in but
teaches no port. Turn on **Always ask for the seat PIN** (`CHECKIN_REQUIRE_PIN`) to refuse typed
seats without their PIN.
