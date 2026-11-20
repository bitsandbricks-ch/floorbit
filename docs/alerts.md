# Alerts and the Problems page

Floorbit posts to Discord when something breaks (see [integrations.md](integrations.md#discord-alerts)).
These settings and pages keep that useful during an event. Code:
[`integrations/alerting.py`](../integrations/alerting.py), [`floorbit/problems.py`](../floorbit/problems.py)
and [`floorbit/blueprints/problems.py`](../floorbit/blueprints/problems.py).

## Problems page

**Problems** in the sidebar (`/problems`, with the number of switches down next to it) lists everything wrong right now, worst and oldest first,
with a count of what is down next to the link. Its browser tab starts with the number of problems
that are down or need a look, muted ones (switches and services) left out, e.g. "(2) Problems · Floorbit":

- the monitoring source (LibreNMS) not answering;
- placed switches that are offline;
- red and amber services on the [health wall](health.md);
- high and medium [security findings](security.md). Accounts without `seats.view` see the kind and
  the switch port only, since titles and seats can point at a person;
- [power circuits](power.md) that tripped, are about to, or are getting close;
- the [bandwidth forecast](forecast.md) reaching the warning share of the line within the next hours;
- [links between switches](topology.md) that are down (red) or came up slower than planned (amber).

It asks nothing new: it reads what the status monitor, the health wall, the security watch, the
power layer and the link reader already know. Anyone with `floorplan.view` may see it. **Open** on an offline switch,
and its name in the list of muted switches, open that switch on the floor plan (`/plan`), in its hall.

When the list holds more than one kind, a row above it shows one kind at a time (switches,
services, power, …) with how many of each. The choice is kept in the address (`/problems?kind=power`),
so a reload or a shared link shows the same.

For people who see the [incident board](incidents.md), an offline switch has **Make an incident**:
one click puts it on the board with the switch and the problem's title. Once an incident for that
switch is open, the button becomes **Incident open**, which opens the board filtered to the switch (`/incidents?q=switch:sw-a-01`).

**Copy list** in the page header copies the problems shown (after the kind filter) as plain text,
with the time, the counts and the mutes, for pasting into the crew chat or a ticket.

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
| Log | with the [syslog receiver](syslog.md#log-alerts) on, a line about err-disable, port security, DHCP snooping, MAC flapping, a loop, storm control or a spanning tree change |
| IP range | a seat has an address outside the ranges of its block (see [Firewalls](firewalls.md#seats-in-the-wrong-range)) |
| Port config | a seat port's config breaks a rule in the last config backup (see [Switch configs](configs.md#seat-port-check)) |
| Shared port | the last MAC table read found more than one machine on a seat port, or a switch or router at the seat (see [Cables](cables.md#machines-on-the-seat-ports)) |

A port belongs to a seat when its description (ifAlias) names the seat, such as `Seat A-12` or
`A-12 desk`; **Open** then goes to that seat on the floor plan, otherwise to the switch
(`/plan?seat=A-12`, `/plan?switch=sw-a-01`). The floor plan opens the hall the seat or switch is in
and shows its panel. Entries clear on their own once the port behaves. They hold the
switch, port and seat, never who sits there, so everyone who may see the floor plan may see them.
They don't go to Discord: there can be dozens during an event. Live updates send `attention.changed`.
Code: [`floorbit/attention.py`](../floorbit/attention.py).

## Muting a switch or a service

A switch someone is working on, or that is off on purpose, can be muted for 30 minutes up to a day
(**Mute** on its problem). While muted, it sends no "offline" or "back online" message; it stays on
the Problems page, marked muted, and under **Muted switches and services** until the mute ends or someone presses
**Unmute**. Still at it when the time is nearly up? **+30 min** next to it makes the mute last half an
hour longer and keeps who set it and why (at most 7 days from now). In its last 10 minutes a mute
shows "ends in N minutes", so nobody is surprised when the alerts come back.
On the floor plan a muted switch has a small bell-off badge on its pin, and its tooltip says until
when, so a red pin someone is already on doesn't send a second tech. Right-click a switch to
**Mute alerts…**, or on a muted one **Mute 30 minutes longer** and **Unmute**, without leaving the
floor plan (crew with `incidents.work`).

A service on the [health wall](health.md) that is red or amber has the same **Mute**: while muted, Discord
gets no "is down" or "is back" message for it, and it stays out of the counts in the browser tab.
It stays on the health wall in its colour, with "alerts muted until" and the time on its tile (who muted it and why are on the Problems page), and out of the health wall's tab count. Muting needs `incidents.work` and is in the audit log under **alerts**. Mutes are stored
in `data.json` under `alert_mutes` and survive a restart.

When a mute runs out and the switch is still offline (or the service still red), Discord gets one
"🔔 Mute on … ended: still offline" message with the reason the mute was given, and the usual
mention. Without it nobody would hear again: the down message was held back while muted, and
nothing changes when the mute ends. The check runs with every switch status poll and health wall
change. A mute someone lifts with **Unmute** says nothing, and a switch that came back while muted
says nothing either.

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
