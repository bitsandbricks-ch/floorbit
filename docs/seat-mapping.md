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
