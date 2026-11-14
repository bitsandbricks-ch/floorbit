# Alerts and the Problems page

Floorbit posts to Discord when something breaks (see [integrations.md](integrations.md#discord-alerts)).
These settings and pages keep that useful during an event. Code:
[`integrations/alerting.py`](../integrations/alerting.py), [`floorbit/problems.py`](../floorbit/problems.py)
and [`floorbit/blueprints/problems.py`](../floorbit/blueprints/problems.py).

## Problems page

**Problems** in the top bar (`/problems`) lists everything wrong right now, worst and oldest first,
with a count of what is down next to the link:

- the monitoring source (LibreNMS) not answering;
- placed switches that are offline;
- red and amber services on the [health wall](health.md);
- high and medium [security findings](security.md). Accounts without `seats.view` see the kind and
  the switch port only, since titles and seats can point at a person;
- [power circuits](power.md) that tripped, are about to, or are getting close;
- the [bandwidth forecast](forecast.md) reaching the warning share of the line within the next hours.

It asks nothing new: it reads what the status monitor, the health wall, the security watch and the
power layer already know. Anyone with `floorplan.view` may see it.

## Needs attention

Below the problems, **Needs attention** lists ports an ops person should look at, newest first.
Every `ATTENTION_INTERVAL` seconds (120) Floorbit reads all ports of the switches that are placed and
online from the monitoring source (`device_ports`, one request per switch to LibreNMS) and keeps what
it saw last time:

| Entry | When |
| --- | --- |
| Flapping | the link went up or down `ATTENTION_FLAPS` times (3) within ten minutes |
| Errors | the error counters (in and out) grew by `ATTENTION_ERRORS` (10) or more since the last read |
| Duplex | a port that is up runs at half duplex: usually a bad cable or a forced speed setting |
| Check-in | with [check-in](integrations.md#seat-check-in-page) on, a seat's port is up while nobody checked in at that seat |

A port belongs to a seat when its description (ifAlias) names the seat, such as `Seat A-12` or
`A-12 desk`; **Open** then goes to that seat on the floor plan, otherwise to the switch
(`/?seat=A-12`, `/?switch=<id>`). Entries clear on their own once the port behaves. They hold the
switch, port and seat, never who sits there, so everyone who may see the floor plan may see them.
They don't go to Discord: there can be dozens during an event. Live updates send `attention.changed`.
Code: [`floorbit/attention.py`](../floorbit/attention.py).

## Muting a switch

A switch someone is working on, or that is off on purpose, can be muted for 30 minutes up to a day
(**Mute** on its problem). While muted, it sends no "offline" or "back online" message; it stays on
the Problems page, marked muted, and under **Muted switches** until the mute ends or someone presses
**Unmute**. Muting needs `incidents.work` and is in the audit log under **alerts**. Mutes are stored
in `data.json` under `alert_mutes` and survive a restart.

## Big outages are one message

When more switches change in one poll than `ALERT_GROUP_AFTER` (3), Discord gets one message per
direction ("🔴 8 switches offline") listing them by [power circuit](power.md), so a row losing power
reads as one line:

```
Circuit B row 1: sw-b-01, sw-b-02, sw-b-03
Other: sw-a-01
```

## Quiet hours

`ALERT_QUIET_HOURS` (for example `02:00-08:00`, in the server's time zone; set `TZ` in Docker) keeps
every message, but sends it silently and without `DISCORD_MENTION`, so the night shift can read it
and nobody's phone rings. Windows over midnight (`23:00-07:00`) work. A value Floorbit can't read
means no quiet hours.

## Not in this version

Discord alerts for a single port going down or errors rising need to know which ports matter (uplinks
and trunks, not seats where players come and go); the needs-attention list shows them without
paging anyone. TODO: ask Mike which alerts matter most at the event, and whether uplink ports can
come from the inventory.
