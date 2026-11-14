# Tournament seats

**Tournament seats** (`/tournament`, linked from Settings) marks the seats where matches are played.
A match zone has a name ("Main stage"), its seats and an optional note. Seats are given as whole
blocks (`B`), single seats (`A-3`) and ranges (`A-1..A-16`), separated by commas. Changing zones
needs `floorplan.edit` and goes to the audit log.

## What a match seat changes

- **First in every list:** its needs-attention items (flapping, rising errors, half duplex, online
  without a check-in) come first on the Problems page, and its incidents first in their column on the
  incident board. Both carry a "Match seat" badge with the zone.
- **Port actions ask twice:** bouncing, shutting or turning on a match seat's port (from the floor
  plan or a security finding) first answers 409 with the zone; the dialog says it is a match seat and
  the action only runs after a second click. Actions on a switch and port without a seat aren't
  checked.
- **Floor plan:** match seats have a gold outline in the editor, and the tournament page shows each
  hall with them marked.

## Ports to prioritise (QoS)

**Look up ports** lists, per switch, the ports whose description names a match seat (the same
"Seat A-12" descriptions the needs-attention watch reads) and the switch's uplinks, so the network
team can give them priority on the switches. Seats not found on any port are listed too. Floorbit
doesn't change the switch configuration itself.

## API

| Request | Needs | What |
| --- | --- | --- |
| `GET /api/tournament` | `floorplan.view` | Zones, seat -> zone, and each hall's plan with the match seats |
| `GET /api/tournament/seats` | `floorplan.view` | Seat -> zone, for the editor |
| `POST /api/tournament/zones` | `floorplan.edit` | `{"name", "seats": "B, A-1..A-4", "note"}` |
| `PATCH`/`DELETE /api/tournament/zones/<id>` | `floorplan.edit` | Change or remove a zone |
| `GET /api/tournament/qos` | `floorplan.view` | Ports behind match seats per switch, uplinks, seats not found |

Port actions take `"confirm_match": true` as the second confirmation.
