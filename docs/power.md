# Electrics: power circuits and load

The **Electrics** page (`/power`, **Electrics** in the sidebar under Network) is for the Electrics team. It lists the
distribution boards, the circuits each one feeds and the load on every circuit as a percentage of its
fuse. The **Power circuits** layer on the floor plan colours every seat and switch by its circuit, so
ops can see what goes dark when a breaker trips. On the **Seats** page (`/plan`), the **Power** switch draws each placed board as a box
and a cable from it to what each circuit feeds (the middle of its seats, and its switches), coloured
by the circuit's load and dashed when it tripped. Under each board, a bar and a number show its busiest circuit's load, or how many of its circuits tripped. The page's browser tab starts with the number of circuits that are
getting close, about to trip or tripped, e.g. "(2) Electrics · Floorbit". Code: [`floorbit/power.py`](../floorbit/power.py)
and [`floorbit/blueprints/power.py`](../floorbit/blueprints/power.py).

## Boards and circuits

- A **board** has a name (DB-1), where it hangs, and optionally a spot on the floor plan (percent
  from the left and top), where the power layer draws it.
- A **circuit** comes from one board and has a name, a phase (L1, L2, L3 or 3P for a three-phase
  feed), a fuse rating in amps and, when a meter reports it, the meter's id. It feeds whole seat
  blocks, single rows of a block (counted from the top as drawn), and switches.

Boards and circuits are stored in `data.json` under `power`. A board keeps its circuits: remove or
move them first.

Every board and circuit has its own page: `/power/boards/<id>` lists the board's circuits and is
where it is changed or removed; `/power/circuits/<id>` shows the load, takes a reading, has
**Mark as tripped** / **Back on** (only red once the breaker tripped), lists what the circuit feeds and is where it is changed or removed. The
list only links to them. **Add board** and **Add circuit** open `/power/boards/new` and
`/power/circuits/new` (`?board=<id>` starts it on that board).

## Load

The load is the newest reading: typed in on the circuit's page (in amps or watts) or sent by a
power plugin. Watts become amps at `POWER_VOLTAGE` (230 V). For a 3P circuit, enter the busiest phase.

| Colour | When | What happens |
| --- | --- | --- |
| Green | under `POWER_WARN` (80 %) | |
| Amber | from `POWER_WARN` | shows on the page and the layer |
| Red | from `POWER_CRIT` (95 %) | an incident for the Electrics team, a Discord message, the `power.alert` hook |
| Red, hatched | someone pressed **Mark as tripped** | the same, with "Breaker tripped" |
| Grey | no reading yet | |

The incident goes to the team in `POWER_TEAM` (`electrics`, one of the default teams) and names
the board, the phase and what the circuit feeds ("12 seats (A-1 to A-12) and switches sw-a-01").
There is one open incident per circuit: staying red, or tripping while it is open, adds no second
one. After a restart, circuits that are already red page nobody again. `POWER_INCIDENTS` off keeps
the alerts but files no incidents.

## Who may do what

| | Needs |
| --- | --- |
| See the page, the layer and the load | `floorplan.view` (seat numbers and switch names only, no personal data) |
| Add and change boards and circuits | `power.edit` (Admin and Lead), or `power.edit` in a team role of the Electrics team |
| Enter readings, report a trip and "back on" | the above, or `incidents.work` in the Electrics team (a Tech there) |
| Read the meters now | `plugins.run` |

Every change, reading and trip is in the audit log under **power**.

## Meters and smart PDUs

Floorbit talks to no meter itself: a plugin with `uses: [power]` does. Its `power_readings()`
returns the load per meter id:

```python
def power_readings(self):
    return [{"meter": "db1-1", "amps": 12.4}, {"meter": "db1-2", "watts": 2100}]
```

A circuit with that meter id takes the reading. It is asked every `POWER_INTERVAL` seconds (60);
a plugin that fails keeps its last readings, which age on the page. The **Demo data** plugin has
meters for every demo row: B row 2 runs warm and C row 2 goes red two minutes in seven.

### Shelly and Home Assistant

Two plugins from the [Marketplace](marketplace.md) read meters on the event network through the
[local agent](agent.md), so they work with a hosted Floorbit too (bitsandbricks-ch/floorbit-plugin-shelly
and bitsandbricks-ch/floorbit-plugin-home-assistant). Install them under **Settings > Plugins >
Marketplace** and turn them on; the agent fetches them, signed, within a minute and sends the
newest readings only.

- **Shelly meters**: one line per meter, `meter id = address [channel]`, e.g. `db1-1 = 192.0.2.50`
  or `db1-2 = 192.0.2.51 em:0`. Later generations are asked `/rpc/Shelly.GetStatus`, the first
  generation `/status`. Without a channel, all of a Shelly's channels are added up. A password is
  optional, the same for all of them.
- **Home Assistant meters**: the URL, a long-lived access token (read access is enough) and one line
  per meter, `meter id = sensor.entity_id`. The sensor's unit decides: `W`, `kW` or `A`.

A Shelly that refuses the password, or a Home Assistant that refuses the token, is reported once on
**Local agents** and audit-logged, and not asked again until a tech clears it there or the password
or token is changed in the plugin's settings. A meter the agent hasn't read for five minutes counts
as unread.

TODO: ask Mike which PDUs or meters are used at the event, and whether any report load, so a
plugin can read them.

## Settings

Under **Settings › Electrics**:

| Setting | Default | |
| --- | --- | --- |
| `POWER_ENABLED` | on | the page, the nav link and the layer; off for installs that don't track power |
| `POWER_WARN` | `80` | amber from this % of the fuse |
| `POWER_CRIT` | `95` | red, incident and alert from this % |
| `POWER_VOLTAGE` | `230` | for readings in watts |
| `POWER_INTERVAL` | `60` | seconds between meter readings, min 15 |
| `POWER_TEAM` | `electrics` | the team id power incidents go to |
| `POWER_INCIDENTS` | on | file incidents for red and tripped circuits |
| `DISCORD_POWER_ALERTS` | on | under Discord alerts |

## API

| Request | |
| --- | --- |
| `GET /api/power` | boards, circuits with `state`, `load_pct`, `reading` and `fed` (seats, switches) |
| `GET /api/power/markers` | per seat and switch the circuit and state; the placed boards |
| `POST /api/power/boards`, `PATCH`/`DELETE /api/power/boards/<id>` | boards |
| `POST /api/power/circuits`, `PATCH`/`DELETE /api/power/circuits/<id>` | circuits: `board`, `name`, `phase`, `rating_a`, `meter`, `blocks: [{block, rows}]`, `switches` |
| `POST /api/power/circuits/<id>/reading` | `{"amps": 12.5}` or `{"watts": 2900}` |
| `POST /api/power/circuits/<id>/trip` | `{"tripped": true}` or `false` when it is back on |
| `POST /api/power/check` | ask the power plugins now |

Live updates: `power.changed` after every change, `power.alert` when a circuit turns red or trips.
