# Event replay

**Replay** (`/replay`, linked from the stats page) plays the whole event back on the floor plan: how
the hall filled up, when traffic peaked, and where the incidents were. A time slider, play and
pause, and a heatmap of every seat block to click on to jump to a moment. With more than one hall,
a picker at the top switches between them.

It needs `floorplan.view` and shows seat numbers and times only: no nicks, IPs or MACs.

## The recording

The replay plays a recording of the whole event (`floorbit/recording.py`). The port watch writes a
frame to it every five minutes: bandwidth, seats online, which seats were online, which had an open
incident, and per seat block the seats, how many were online, their traffic and their open
incidents. Seat numbers and numbers only.

Older frames are thinned out once an hour, so a long event stays small:

| Age | One frame every |
| --- | --- |
| last 24 hours | 5 minutes |
| up to a week | 30 minutes |
| older | hour (at most 5,000 frames) |

The frames go to `recording.jsonl` next to `data.json` (or the file `RECORDING_FILE` names) and
start over when the event is closed on the [Events](events.md) page, or with **Only start the figures
again** there.

Below the plan, the **heatmap** shows every seat block over time: seats online (share of the
block), traffic, or open incidents. Click a column to jump there.

**Download JSON** (`GET /api/replay/event.json`) gives every frame of every hall.

## What it doesn't show

- **Switches going down and coming back** are not kept as history yet (only their current state and
  the incidents filed for them), so the replay doesn't show them.
- **Per-seat traffic over time** is kept per block, not per seat.
