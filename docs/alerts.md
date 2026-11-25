# Alerts and the Problems page

Floorbit posts to Discord when something breaks (see [integrations.md](integrations.md#discord-alerts)).
These settings and pages keep that useful during an event. Code:
[`integrations/alerting.py`](../integrations/alerting.py), [`floorbit/problems.py`](../floorbit/problems.py)
and [`floorbit/blueprints/problems.py`](../floorbit/blueprints/problems.py).

## Problems page

**Problems** in the sidebar (`/problems`, with the number of switches down next to it) lists everything wrong right now, worst and oldest first,
with a count of what is down next to the link. Its browser tab starts with the number of problems
that are down or need a look, muted ones left out, e.g. "(2) Problems · Floorbit":

- the monitoring source (LibreNMS) not answering;
- placed switches that are offline;
- red and amber services on the [health wall](health.md);
- high and medium [security findings](security.md), with the evidence on the problem's page; low ones
  come with the seat and port trouble. Accounts without `seats.view` see the kind and the switch
  port only, since titles and seats can point at a person;
- [power circuits](power.md) that tripped, are about to, or are getting close;
- the [bandwidth forecast](forecast.md) reaching the warning share of the line within the next hours;
- [links between switches](topology.md) that are down (red) or came up slower than planned (amber);
- [Wi-Fi](wifi.md) access points that are down (red) or busy for 5 minutes (amber), and two placed
  access points near each other on one channel (amber);
- plugins turned on that don't load (red), whose calls have all failed for 5 minutes (amber), and
  installed versions the [Marketplace](marketplace.md) withdrew (amber);
- [alerts LibreNMS pushed through the agent](librenms-alerts.md), until their recovery.

It asks nothing new: it reads what the status monitor, the health wall, the security watch, the
power layer, the link reader and the Wi-Fi view already know. Anyone with `floorplan.view` may see it. **Open** on an offline switch,
and its name in the list of muted switches, open that switch on the floor plan (`/plan`), in its hall.

Seat and port trouble (see [Seats with trouble](#seats-with-trouble) below) is part of the same
list. The list is a table: type, the problem (title, where, what it cuts off, its mute), when it
started and the actions. It is sorted by **priority**, then muted ones last, and within each the
longest standing first:

1. **Urgent**: down and cutting off more than itself: a switch or link with switches behind it or
   with 20 seats or more on it, or a router, firewall, core or distribution box (its role in the
   inventory);
2. the rest that is down;
3. what needs a look.

People with `incidents.work` can **Raise** any problem to urgent by hand when the rules don't know
it matters more (it shows **Raised**, with who did it), and **Lower again**. A raise is forgotten
after 7 days. **Started** and **Problem** sort it the other ways. The cards on top count what is down, what
needs a look, the **seats with trouble** (counted like the floor plan's "!": check-in left out) and
what is muted.

The list folds what belongs together (issue #1415):

- The same problem on three seats or more is **one row**, e.g. **9 seats online without a check-in**;
  **Show the 9 seats** lists them, each opening its own page. Picking that kind or **Seats** above
  the list shows them one row each again, and a muted or raised one keeps its own row.
- A link that is down because the box at one of its ends is down hangs **under that box**
  (**Its link is down too: …**) instead of being a row of its own: the box is where to start.
- **Started** is when the problem was first seen and stays so across a restart of Floorbit, so
  rows don't all say "now" after an update.
- Each row keeps to one line of actions: **Open**, its incident or **Report**, and the rest
  (**Mute**, **Raise**, **Swap**, **Clear**) under **…**.

Above the list, one row holds a search and the filters, each a menu that names its choice, like
every other list in Floorbit. **Search** looks through the title, where it is, the switch, the seat
and the hall (`?q=sw-a`). The filters, all kept in the address so a reload or a shared link shows
the same:

- **Type**: one kind at a time (switches, services, power, …) with how many of each (`?kind=power`);
  **Seats** shows everything about a seat, whatever its kind;
- **Severity**: all, only what is down, or only what needs a look (`?level=down`, `?level=warn`);
- **Group by**: nothing, type, switch (`?group=device`) or, with more than one hall, hall
  (`?group=hall`). Grouped, each gets its own table under its name with a count and how many are
  down; problems on no switch (a service, the forecast) come last under **Not on a switch** (or
  **No hall**). The hall is the one the switch is placed in, or for seat trouble the seat's block;
- **Tag**: only problems on a switch with that tag in the inventory (`?tag=stage`);
- **Muted**: shown or hidden (`?muted=hide`).

A group's name folds it away, for one someone is already on: it stays folded in this browser across
reloads, and **Fold all** / **Unfold all** next to the filters fold every group at once. Grouped,
the list comes in pages of 10 groups (25 or 50 on demand), so a group never splits across pages;
ungrouped it comes in pages of 50 rows, the page and the sort in the address too (`/problems?page=2`).

For people who see the [incident board](incidents.md), an offline switch has **Make an incident**:
one click puts it on the board with the switch and the problem's title. Once an incident for that
switch is open, the button becomes **Incident open**, which opens the board filtered to the switch (`/incidents?q=switch:sw-a-01`).

Each problem's title opens **its own page** (`/problems/<id>`): what it is and where, since when,
the seats it cuts off, and links to look further (where it was seen, the device in the inventory,
the seat or switch on the floor plan, and for `seats.view` its logs and the machines seen at the
seat). With `seats.view` it also lists the newest 20 syslog lines of the seat (or the switch,
when the problem has no seat), every 15 seconds, with **Open in Logs** for more. **Make an incident** works there and in the list for every problem on a seat or a switch:
the incident remembers the problem it came from and links back to it, and the problem shows
**Incident open** while it is. A problem that is over says so; its incident stays on the board.
A problem is what Floorbit sees and ends by itself; an incident is the work someone does about it.

**Copy list** in the page header copies the problems shown (after the filters) as plain text,
with the time, the counts and the mutes, for pasting into the crew chat or a ticket.

## Seats behind a failure

A down switch or a down link between switches (issue #950) says what it cuts off: "24 seats
affected · 2 switches behind it", with the seat names one click away. Seat names only, never who
sits there.

- **Behind** comes from the links on the [topology](topology.md): a switch is cut off when no path
  of up links through online boxes reaches the core. The core is the routers and firewalls the links
  reach; where the links name none, each group of linked switches takes its busiest switch (the most
  links). Without links only the down switch's own seats count.
- **A switch's seats** come from every place that knows them: the last port read, what was
  remembered while the switch went down, the seat mapping, ports learned at check-in or on the seat
  walk, and the patch plan's cables.
- When the switch before it dies, monitoring loses the ones behind too. Those say **"Behind
  sw-a-01, which is down: start there"**, so the crew goes to the cause first.
- On the floor plan every seat cut off turns red (offline), for attendees too; the crew's plan also
  knows which switch or link is to blame.
- A single seat port that goes down takes only that seat, which the plan already shows as offline.

## Seats with trouble

After the problems, the list holds ports and seats an ops person should look at, newest first.
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
| Incident | an open [incident](incidents.md) on a seat (also what attendees report at their seat); **Open** shows the board filtered to that seat |
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

## Muting a switch, a service or an access point

A switch someone is working on, or that is off on purpose, can be muted for 30 minutes up to a day
(**Mute** on its problem). While muted, it sends no "offline" or "back online" message; it stays on
the Problems page, marked muted, and under **Muted alerts** until the mute ends or someone presses
**Unmute**. Still at it when the time is nearly up? **+30 min** next to it makes the mute last half an
hour longer and keeps who set it and why (at most 7 days from now). In its last 10 minutes a mute
shows "ends in N minutes", so nobody is surprised when the alerts come back.
On the floor plan a muted switch has a small bell-off badge on its pin, and its tooltip says until
when, so a red pin someone is already on doesn't send a second tech. Right-click a switch to
**Mute alerts…**, or on a muted one **Mute 30 minutes longer** and **Unmute**, without leaving the
floor plan (crew with `incidents.work`).

A Wi-Fi access point that is down or busy has a **Mute** too: muted, it stays on the list and in the
Wi-Fi view but out of the counts. Its mute key is `wifi:<name>`.

Every other problem on the list (a link, a power circuit, port trouble, a log alert, a plugin, …) has
**Mute** too, with the same time limit (issue #887): muted, it stays on the list, marked, and leaves
the counts (sidebar, tab title, bell, handover) until the mute ends; under **Muted alerts** its name
opens its page. Its mute key is `problem:<problem id>`, and the API takes `{"problem_id", "minutes",
"reason"}`. These problems send no Discord messages of their own, so a mute only quiets the counts.

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
