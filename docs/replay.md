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

## The whole event

**Whole event** at the top of the page switches from the last 24 hours to a recording of the whole
event (`floorbit/recording.py`). The port watch writes a frame to it every five minutes: bandwidth,
seats online, which seats were online, which had an open incident, and per seat block the seats,
how many were online, their traffic and their open incidents. Seat numbers and numbers only.

Older frames are thinned out once an hour, so a long event stays small:

| Age | One frame every |
| --- | --- |
| last 24 hours | 5 minutes |
| up to a week | 30 minutes |
| older | hour (at most 5,000 frames) |

The frames go to `recording.jsonl` next to `data.json` (or the file `RECORDING_FILE` names) and
start over with **Start a new event** on the [report](report.md) page.

Below the plan, a **heatmap** shows every seat block over time: seats online (share of the block),
traffic, or open incidents. Click a column to jump there.

**Export:**

- **Download JSON** (`GET /api/replay/event.json`): every frame of every hall.
- **Record video** plays the recording onto a canvas in the browser and saves it as a WebM video
  (at most 75 seconds, longer events skip frames). It needs a browser with `MediaRecorder`
  (current Chrome, Edge and Firefox); without one the button is hidden.

## What would need more history

- **Switches going down and coming back** are not kept as history yet (only their current state and
  the incidents filed for them), so the replay doesn't show them.
- **Per-seat traffic over time** is kept per block in the whole-event recording, not per seat.
