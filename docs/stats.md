# Stats dashboard

**Stats** in the top bar (`/stats`) has the numbers people ask for during the event:

| Tile | What it is |
| --- | --- |
| Now | traffic to and from the players right now, with download (↓) and upload (↑) |
| Peak, last hour / 24 hours | the busiest read in that time, and the average |
| Peak of the event | the busiest read since the peak was last reset |
| Seats online | seat ports that are up, and the most in the last 24 hours |
| Ports | ports up, down and with errors |

Below them: traffic over the last hour or 24 hours, **Uplinks** (how full each switch's uplink is,
amber from 60 %, red from 80 %) and **Top talkers** (the ten ports with the most traffic right now).

Code: [`floorbit/stats.py`](../floorbit/stats.py), [`floorbit/blueprints/stats.py`](../floorbit/blueprints/stats.py),
[`frontend/src/pages/Stats.tsx`](../frontend/src/pages/Stats.tsx).

## Where the numbers come from

Floorbit asks nothing extra for them. The [needs-attention watch](alerts.md#needs-attention)
already reads every port of the placed, online switches from the monitoring source (LibreNMS)
every `ATTENTION_INTERVAL` seconds (120); each read becomes one sample here.

- **Bandwidth** is download plus upload summed over the access ports, so traffic between two players
  counts at both seats. Uplinks are left out, so a frame isn't counted again on its way up.
- **Seats online:** a port belongs to a seat when its description (ifAlias) names it, such as
  `Seat A-12`. Ports without a seat (servers, the stage) count towards bandwidth but not seats.
- **Uplinks:** per switch, its busiest up port whose description matches `STATS_UPLINK_PATTERN`
  (`uplink|trunk`, case-insensitive) or names another switch in the inventory, such as `to dist-01`.
  TODO: ask Mike whether uplinks should come from the inventory (NetBox cables) instead.

Samples are kept for 24 hours, together with the event's peak and the moments each seat went online
or offline (for the [replay](replay.md)), in Redis under `floorbit:stats`,
so a restart doesn't lose them. Without Redis they live in memory until the next restart. For the
[event report](report.md), each read is also folded into one row per hour, kept for 21 days.

**Reset peak** (needs `settings.manage`, in the audit log under settings) starts the event's peak
again from the latest read: use it after load tests, before doors open.

## Compare

Under the charts, **Compare** puts today next to yesterday and, once an event has been archived
([past events](events.md)), this event next to the last one. Both sides are cut to the same
length, so the numbers are fair. At 15:00, today is compared with yesterday until 15:00, and an
event in its 20th hour with the last event's first 20 hours.

It shows six rows, each with the change in percent:

- the busiest moment;
- the average bandwidth;
- the data moved;
- the most seats online;
- incidents;
- switch outages.

A dashed line shows the other side's average bandwidth per hour over the whole day or event. The
archive keeps outages per switch but not when they happened, so the event comparison has no "so
far" outage count. The same comparison is on the [report](report.md).

`GET /api/stats/compare` answers `day` (`now`, `then`, `series` per hour of the day, `has_then`) and
`event` (the last event's `name`, `elapsed_s`, `now`, `then`, `series` per hour since the start), or
`null` when no event is archived or past events are turned off.

## On a big screen

**Big screen** (`/stats?screen=1`) drops the header, makes the numbers readable from across the
hall and shows the last hour. Like `/kiosk` and the [health wall](health.md), it gets the kiosk
theme unless the screen picks another one with `?theme=` ([themes.md](themes.md)). It refreshes on
its own after every read.

## Who sees what

Anyone with `floorplan.view` sees the page. Samples hold numbers, seats and ports, never who sits
there. Accounts with `seats.view` see the player's nick next to a top talker; the big-screen version
never shows nicks, because everyone in the hall can read it. IPs and MACs are never shown here.
