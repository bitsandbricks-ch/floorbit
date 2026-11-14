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

## Brackets

**Brackets** (`/tournament/brackets`, from the Tournament seats page) are single-elimination
tournament trees for the crew and the big screens.

- **New bracket:** a name, an optional match zone and the teams, one per line, best seed first. The
  teams are seeded 1 against the last, 2 against the second-to-last and so on, and byes fill the
  bracket up to 4, 8, 16 … teams: the top seeds get them and move on by themselves.
- **Results:** click a match to enter the scores, the winner, whether it is live, its station and its
  seats ("A-1..A-5, B-1..B-5"). The winner moves to the next round; changing a result takes the
  wrong team back out of the later rounds. A match's seats link to the floor plan and name the
  match zone they are in.
- **From a tournament tool:** a plugin that uses `brackets` (see [plugins](plugins.md#areas-uses))
  sends brackets; **Import from …** asks it again. Imported brackets are read-only here and replaced
  on every import; only their match zone can be set. The demo data has one.

Changing brackets needs `floorplan.edit`; every change is in the audit log.

### The public view

`/bracket` shows the brackets for attendees and the big screens (`?screen=1`, `?id=<bracket>` for
one of several): team names, scores, which match is live, the station and the champion, and the
match zone's name. Never seats. It reloads every 30 seconds; `/bracket.json` has the same. It is off
until **Settings > Attendee pages > Tournament brackets** (or `BRACKET_VIEW=true`) turns it on.

## API

| Request | Needs | What |
| --- | --- | --- |
| `GET /api/tournament` | `floorplan.view` | Zones, seat -> zone, and each hall's plan with the match seats |
| `GET /api/tournament/seats` | `floorplan.view` | Seat -> zone, for the editor |
| `POST /api/tournament/zones` | `floorplan.edit` | `{"name", "seats": "B, A-1..A-4", "note"}` |
| `PATCH`/`DELETE /api/tournament/zones/<id>` | `floorplan.edit` | Change or remove a zone |
| `GET /api/tournament/qos` | `floorplan.view` | Ports behind match seats per switch, uplinks, seats not found |
| `GET /api/tournament/brackets` | `floorplan.view` | Every bracket, its matches with their seats and zones, the plugins that send brackets |
| `POST /api/tournament/brackets` | `floorplan.edit` | `{"name", "teams": ["..."], "zone_id"}` |
| `PATCH`/`DELETE /api/tournament/brackets/<id>` | `floorplan.edit` | Rename it, set its zone, or remove it |
| `PATCH /api/tournament/brackets/<id>/matches/<match>` | `floorplan.edit` | `a_score`, `b_score`, `winner` (`a`/`b`/null), `status` (`waiting`/`live`), `seats`, `station` |
| `POST /api/tournament/brackets/import` | `floorplan.edit` | Ask the bracket plugins again |

Port actions take `"confirm_match": true` as the second confirmation.
