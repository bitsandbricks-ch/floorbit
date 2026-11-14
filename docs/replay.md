# Event replay

**Replay** (`/replay`, linked from the stats page) plays the event back on the floor plan: how the
hall filled up, when traffic peaked, and where the incidents were. A time slider, play and pause at
1 minute to 1 hour per second, and a bandwidth chart to click on to jump to a moment.

It needs `floorplan.view` and shows seat numbers and times only: no nicks, IPs or MACs.

## What it uses

All of it is history Floorbit keeps anyway:

| What | From | How far back |
| --- | --- | --- |
| Bandwidth and seats online over time, the event's peak | the [stats](stats.md) reads (every `ATTENTION_INTERVAL`, 120 s) | 24 hours |
| Which seat went online or offline when (its switch port up or down) | the same reads, written down on change only | 24 hours; older changes fold into the starting state |
| Which seats were checked in when | the check-in history (`integrations/history.py`), without who | the whole file |
| Incidents, from filed to fixed, as rings on their seats | the incident board | as long as the board keeps them |

The seat changes are new with the replay: the stats reads already saw every seat port, and now
keep the moments a seat changed (in Redis with the other stats, at most 100,000 changes).

With check-ins in use, the replay can show "checked in" instead of "online".

## What would need more history

- **More than the last 24 hours of port reads.** A whole weekend needs the stats samples and seat
  changes kept longer (more Redis memory) or written to a file like the NetFlow hourly totals. TODO for
  Mike: keep them for the whole event?
- **Switches going down and coming back** are not kept as history yet (only their current state and
  the incidents filed for them), so the replay doesn't show them.
- **Per-seat traffic over time** (a heat replay) would need the per-seat numbers of every read kept.
