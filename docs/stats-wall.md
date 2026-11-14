# Stats wall

`/wall` shows the event in numbers, for a big screen in the hall and for attendees' phones. No account
is needed. It is off until **Settings > Attendee pages > Stats wall** (or `STATS_WALL=true`) turns it on.

What it shows, each only once there is something to show:

| Fact | From |
| --- | --- |
| Seats online now, of all seats | the latest switch port read (unknown after three missed reads) |
| Most seats online at once | the report's hourly history and the [whole-event recording](replay.md#the-whole-event) |
| Downloaded so far | the whole-event recording (download bandwidth over time); without one, the report's hourly averages |
| Bandwidth peak and when | the [stats](stats.md) peak since the last new event |
| Busiest hour | the report's hourly averages |
| Most loyal seat block | the recording: the block whose seats were online the longest, on average |
| Served from the LAN cache | the [LAN cache](games.md) log, if one is set up |
| What the hall plays | the top five launchers and games from [game insights](games.md) |

It reloads every minute. `?screen=1` is the big-screen layout: larger type, no scrolling and no footer.
`/wall.json` has the same numbers for the event website or a Discord bot.

## Privacy

Everything is for the whole hall or for a seat block: no nicks, IPs, MACs, seat numbers or switch
names. A seat block is only named with five seats or more, and the games come from game insights,
which only count sites and services enough seats used (the five-seat rule).
