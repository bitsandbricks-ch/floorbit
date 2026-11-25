# Stats wall

The ready-made **Event in numbers** dashboard (`/dashboards/event`) shows the event in numbers, for a
big screen in the hall and for attendees' phones. It is public, and each of its numbers is a tile of its
own (**Downloaded**, **Busiest moment**, **Most seats online**, **Busiest hour**, **Most loyal block**,
**From the LAN cache**, **Top games**, **Most downloaded**, **Top sites in the hall**) that can go on any public dashboard too. No account
is needed. It is off until **Settings > Attendee pages > Stats wall** (or `STATS_WALL=true`) turns it on;
while it is off, those tiles say so on public screens and `/wall.json` answers anonymous callers
with 404. The setting is about the public side only: signed-in crew always see the numbers, on
their own dashboards and in `/wall.json`.

What it shows, each only once there is something to show:

| Fact | From |
| --- | --- |
| Seats online now, of all seats | the latest switch port read (unknown after three missed reads) |
| Most seats online at once | the report's hourly history and the [whole-event recording](replay.md#the-recording) |
| Downloaded so far | the whole-event recording (download bandwidth over time); without one, the report's hourly averages |
| Bandwidth peak and when | the [stats](stats.md) peak since the last new event |
| Busiest hour | the report's hourly averages |
| Most loyal seat block | the recording: the block whose seats were online the longest, on average |
| Served from the LAN cache | the [LAN cache](games.md) log, if one is set up |
| Top games | the five game titles the most seats played, from [applications](applications.md): the most seats DNS, traffic or the event's game servers saw, and which of them saw it |
| Most downloaded | what the LAN cache served: per game where the Steam depots say so, else per launcher (less what its games already count) or site group such as Windows updates; and how much came from the cache's disks |
| Top sites in the hall | the five sites the most seats looked up, each with its kind (gaming, streaming, social, ...). Only sites of a known application: the open lists Floorbit ships, or the event's own |

It updates every minute in place, without reloading (see [Public pages stay current](status-page.md#staying-current)).
`/wall.json` has the same numbers for the event website or a Discord bot.

## Privacy

Everything is for the whole hall or for a seat block: no nicks, IPs, MACs, seat numbers or switch
names. A seat block is only named with five seats or more, and the games, downloads and sites come
from game insights, which only count sites and services enough seats used (the five-seat rule). The
top sites go one step further: a site that belongs to no application is never shown, however many
seats looked it up.
