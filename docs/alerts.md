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
- [power circuits](power.md) that tripped, are about to, or are getting close.

It asks nothing new: it reads what the status monitor, the health wall, the security watch and the
power layer already know. Anyone with `floorplan.view` may see it.

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

Alerts for a single port going down or errors rising need to know which ports matter (uplinks and
trunks, not seats where players come and go). TODO: ask Mike which alerts matter most at the event,
and whether uplink ports can come from the inventory.
