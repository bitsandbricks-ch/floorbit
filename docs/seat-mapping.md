# Seat mapping

The seat mapping says which **switch port** each seat is on. That is the key: the IP and MAC of the
machine on the seat are read off that port (the switch's MAC table gives the MAC, the core's ARP
table its IP), and the nick comes from check-in or a seat source. The floor plan uses it to show who
sits where, for port actions (bounce, shut) and for the heatmap. Floorbit owns the mapping: it works
with no plugin at all, typed in by hand on the **Seat mapping** page (`/seat-mapping`), and cables,
check-ins, plugins and `seats.json` fill it too.

## Where each field comes from

Floorbit asks every seat source and merges what they send, field by field. The first source
with a value for a field wins:

1. **Hand entries** from the Seat mapping page. Always first, so what you type wins.
2. **Cables and check-ins** (`ports`): a cable that ends at the seat (Cables page), else the port a
   check-in found the seat's machine on.
3. **Switch MAC tables** (`network`): the MAC and IP on the seat's port, from the last read of the
   seat switches (at most every two minutes, started when the page is open). A port with two or more
   machines on it gives none, rather than a guess.
4. **Plugins** with `uses: [mapping]` that are turned on.
5. The sources in `SEAT_SOURCES` (`json` for `seats.json`, `checkin`, `http`), in that order.
   See [integrations](integrations.md#seat--user--ip-sources).

So an IP or MAC typed in or imported only matters for a seat whose port is not known yet. A field
you leave empty on a hand entry is filled from the other sources. The page shows which source gave
each field, so you can see why a seat has the IP it has. Removing a hand entry brings the other
sources' values back.

One port belongs to one seat: a hand entry can't take a port another hand entry has.

## Finding a port by MAC

In the seat's form, **Find the port by MAC** looks up where a machine is plugged in right now: type
its MAC (any spelling) and Floorbit asks the monitoring source which switch port it is on. That fills
the switch and port; save to keep them. It is a helper, not the mapping: you can change the port
again at any time.

Hand entries from before the port was the key have only an IP or MAC. The page offers **Find the
ports** for them once: each gets the port its IP or MAC is seen on now. Seats that aren't on the
network or whose port another seat has are listed and keep what they had.

## Import and export

**Export CSV** downloads the hand entries (`seat,switch,port,ip,mac,nick,note`). **Import CSV**
reads the same columns; leave out the ones you don't have (an older `seat,ip,mac,nick,note` file
still imports). Every row is checked before anything is written: one bad row stops the whole
import and the page lists the lines and what is wrong with them. Import adds and changes seats;
tick *Replace* to also drop hand entries the file doesn't have. MACs can be written any common
way (`AA-BB-CC-DD-EE-FF`, `aabb.ccdd.eeff`) and are stored as `aa:bb:cc:dd:ee:ff`. Cells that a
spreadsheet would run as a formula are escaped in the export.

## Privacy

Nicks, IPs and MACs are personal data:

- The page and its API are for editors and admins only, even when `AUTH_PUBLIC_READ` is on.
- The audit log names the seat and which fields changed, never the values.
- Backups leave the seat mapping out. Keep a CSV export instead if you need one.
  <!-- TODO ask Mike: include the seat mapping in backups (opt in)? -->

## Writing a plugin that feeds it

Add `mapping` to `uses:` and define `seat_mapping()` returning
`{"A-1": {"switch": "sw-a-01", "port": "Gi1/0/11", "nick": "player-one"}}`; `ip` and `mac` are
accepted too, for a source that doesn't know the port. Each field is
optional. Bad entries (a seat label that isn't one, an IP or MAC that doesn't parse) are dropped
and counted, never stored. A plugin that fails shows its error on the Seat mapping page and the
other sources still work.

## API

| Request | What it does |
| --- | --- |
| `GET /api/seat-map` | Every seat with its merged switch, port (and `port_origin`: manual, cable or checkin), ip, mac and nick, which source gave each field, the hand entry, and the sources with their last errors. `?read=1` starts a read of the MAC tables |
| `PUT /api/seat-map/<seat>` | Set the seat's hand entry (`switch`, `port`, `ip`, `mac`, `nick`, `note`); empty fields are dropped |
| `POST /api/seat-map/find-port` | `{"mac"}` or `{"ip"}`: the switch port it is seen on now, and `held_by` when another seat has that port |
| `POST /api/seat-map/resolve-ports` | Give hand entries that have only an IP or MAC their port; `{"dry_run": true}` only says which |
| `DELETE /api/seat-map/<seat>` | Remove the hand entry |
| `GET /api/seat-map.csv` | The hand entries as CSV |
| `POST /api/seat-map/import` | `{"csv": "...", "replace": false, "dry_run": true}`; a dry run only checks |

## Finding a player

The search box on the floor plan (press `/`) finds switches, seats and nicks, and for accounts with
`seats.view` also IPs and MACs (issue #14). A MAC can be written any common way (`02:00:..`,
`02-00-..`, `0200.0000.0009`).

A full IP or MAC is also looked up on the network (`GET /api/seats/find?q=`):

- when no seat source knows it, the DHCP server's lease (when its syslog reaches Floorbit,
  [syslog.md](syslog.md#dhcp-leases-ip-to-mac-as-it-happens)) or else the monitoring source's ARP
  table turns the IP into a MAC (or back) and that finds the seat;
- the switch port it is plugged into is resolved, and shows under **On the network** even when no
  seat is known for it.

Picking a result jumps to the seat, opens it, and the switch it hangs on lights up for a few
seconds. Nicks, IPs and MACs never reach roles without `seats.view`; they still find switches and
seat numbers.

## Checking in from a PC

A PC has no camera, so nobody has to scan the QR code. With check-in on (`CHECKIN_ENABLED`), every
seat card on the printed sheet (Incidents, then Seat QR codes) also carries:

- the **short address** to type, `CHECKIN_ADDRESS` (for example `checkin.example.com`). Point that
  name at the local agent's **front door** in the event DNS (the compose file and the Kubernetes
  manifest open it on port 80, [agent.md](agent.md)); opening it lands on `/checkin`. It also shows
  on the sign-in page.
- the seat's **PIN**: five characters, unique per seat, without look-alikes (no 0/O, 1/I/L, 5/S, 8/B).
  PINs are made the first time the sheet is opened and kept, so a reprint gives the same cards.

The PC's address comes **only from the front door**, the same way whether Floorbit is hosted or
runs in the hall: the agent passes on the address it saw, with its key. Floorbit never takes a
request's own address or `X-Forwarded-For` as the seat PC's. A check-in that didn't come through the
front door (someone opened Floorbit's own address) still keeps the seat and the nick, but no address
and no port (`not_wired`), and the page says to type the short address on the seat PC. With
`CHECKIN_ALLOWED_NETWORKS` set, such a check-in is refused instead.

The attendee types the PIN and their nick, never the seat: the PIN names it. The page answers at
once: the request stores only the seat, the nick, the IP and the time. Everything slow happens in
the background (`verify_pending`, woken by each check-in, then every 10 s): the MAC and the switch
port the PC is on. The attendee's page shows "Finding your seat's network port…" until then.

A PIN works once. After it checked a seat in, only the same PC (same IP) may use it again, to change
the nick, and it may also do that without the PIN. Anyone else gets "That PIN was already used. Ask
the crew"; the crew removes the check-in, which opens the PIN again. A typed seat number can't take
over a seat its card already checked in.

The page tells Floorbit whether it runs on a PC or a phone (the browser's OS hints, touch only and a
small screen, backed by the User-Agent). A phone keeps the nick (`not_wired`) but never teaches a
port. That is only a hint: what proves a wired PC at the seat is the switches. Only a MAC found on
exactly one access port, with no more than 4 MACs on it (so not an AP, a desk switch or an uplink),
counts as `verified`. Not found within 15 minutes: `unverified`.

The lookups run in the background, oldest check-in first, at most **Port lookups per second**
(`CHECKIN_VERIFY_RATE`, 10) with up to ten seconds' worth saved up. At doors-open a thousand
check-ins don't become a thousand LibreNMS lookups at once: they wait their turn and the queue
drains at that rate (measured in [sizing](sizing.md#doors-open)). The check-in page's "you are at
seat …" hint never waits for LibreNMS either: it shows what is already known, and a miss is looked
up in the same background queue, so a reload shows it.

Finding the switch port of the PC takes two steps, because ARP only lives on the core switches: the
request's IP gives the MAC from the core's ARP table, and that MAC is looked up in the MAC tables
(FDB) of every switch. Every switch between the core and the seat learns the MAC too, on its uplink,
so the port with the fewest MACs wins; ports named in "Ignored port names" and ports whose
description matches the uplink pattern (`STATS_UPLINK_PATTERN`) are skipped.

What Floorbit keeps is the pair **seat to switch port** (`seat_ports.json` next to `checkins.json`).
The IP was only the way there. From then on the seat counts as patched to that port wherever the
plan asks (port problems, syslog lines, the seat view, "who is on this port"), and the seat shows
the MAC and IP that are on that port now, from the MAC and ARP tables. A cable drawn in the patch
plan always wins over a learned port.

The Problems page lists check-ins that disagree, as **Seat port** entries: two seats checked in on
the same port, a port the patch plan gives to another seat, or a seat taken over by another nick.
They name the seat and port, never the nick.

The phone page can still take a typed seat number (the QR code case). That records the check-in but
teaches no port. Turn on **Always ask for the seat PIN** (`CHECKIN_REQUIRE_PIN`) to refuse typed
seats without their PIN.

Wrong PINs are counted per PC: after 10 in ten minutes (`CHECKIN_PIN_TRIES`), that PC waits out the
ten minutes before it may try another PIN, so nobody can script their way through the cards. A check-in
from outside `CHECKIN_ALLOWED_NETWORKS` is refused before its PIN is even looked at.

## The crew's Check-in page

**Helpdesk › Check-in** (`/checkins`, needs `seats.view`; listed while check-in is on) is where the crew
watches check-in during the event. It refreshes by itself.

- **Counts:** checked in (and how many seat PINs were used), port found, still looking (and how many
  gave up after 15 minutes), not wired (phones and Wi-Fi: no port to find), and ports to review.
- **Check-ins:** every check-in with its port lookup state, the switch port, IP and MAC, the device
  class the page reported, and when. Filter by state or search a seat, nick, IP, MAC or port. With
  `seats.edit`, **look for the port again** (a gave-up row starts a fresh 15 minutes) or remove the
  check-in.
- **Review:** learned ports that clash: two seats on one port (a small switch under the table, or a
  wrong PIN), a port the patch plan gives to another seat, or a seat whose card was used by another
  nick. **Forget port** drops the learned port of that seat (`DELETE /api/checkins/<seat>/port`).
- **Captive portal:** the local agents' fetches of the checked-in list (DHCP option 114, see
  [integrations](integrations.md)): when, which agent, how many clients counted as done. Kept in
  memory, the last 200. Nothing here unless you add the DHCP option; it is off by default.

The seat inspector on the floor plan shows the same state next to **Checked in** for the crew.
`CHECKIN_ADMIN_TOKEN` still guards the API for scripts; a signed-in crew member doesn't need it,
because the role check already ran.
