# Demo mode

Demo mode fills Floorbit with a made-up LAN, so you can try it without a network. The pull
request screenshots use it too, so they show a filled-in floor plan.

## Turning it on

- Set `FLOORBIT_DEMO=1`, or
- turn on **Demo data** under **Settings > Plugins**.

While it's on, every page shows a **Demo data** badge at the bottom. With `FLOORBIT_DEMO=1` it
stays on and can't be turned off on the Plugins page.

## What you get

The built-in `demo` plugin (`floorbit/builtin_plugins/demo/`) feeds every data area:

- **Inventory:** a common LAN party hardware mix, with real model names and port names:
  - a core router (Cisco Nexus 93180YC-FX: `Ethernet1/1` to `Ethernet1/54`)
  - two distribution switches (Catalyst 4500-X-16: `Te1/1` to `Te1/16`)
  - three access switches for each of the seat blocks A to D, and one for block E (Catalyst
    2960-X-48: `Gi1/0/1` to `Gi1/0/48`, uplink on `Te1/0/1`)
  - ten firewalls behind the core and ten access points
- **Seat mapping:** a player on most of the 112 seats, with:
  - nicks like `player-07`
  - IPs from `192.0.2.0/24`, spread over the ten firewall ranges as DHCP would hand them out
  - locally administered MACs (`02:00:...`)
- **Live data:** this replaces LibreNMS while the demo is on.
  - Status, CPU, memory and temperature for each switch.
  - Every port of every switch: seat ports with traffic that moves slowly, uplinks, the internet
    lines, and the unused ports down.
  - A few heavy downloaders.
  - One seat on half duplex, one with CRC errors.
  - `sw-c-02` goes down for one minute in every four, so you can see alerts and the status monitor work,
    and its 10G uplink came up at 1G.
  - `fw-03` is down, so its seat range has failed over to `fw-04`.

The data is computed from the clock, so it needs no state and looks the same on every instance.
Nothing in it is real: example names, documentation IP ranges (RFC 5737), no real people.

## The floor plan

With `FLOORBIT_DEMO=1`, the demo is laid out once at start-up. This only happens if the floor plan is
still empty, so it never moves anything someone placed. When you turn the demo on from the Plugins page
instead, `POST /api/demo/layout` (admins) does the same. You get:

- **Two halls:** the main hall with seat blocks A to D, and a side hall with block E.
- **Switches** placed above their blocks, each block grouped with its switches so they move as one.
- **Cables:** the seat cables as an import from NetBox would bring them (Cat6, block A in Cat6a through
  the patch panel `PP-A` on the wall), two of them routed by hand with bends, and the uplinks with their
  type and planned speed: 10G multi-mode fiber from the access switches, single-mode fiber to the core,
  DAC to the firewalls.
- **Port areas:** nobody wrote down the side hall's patching, so block E has only rough port areas (ports
  1 to 8 for E-1 to E-8, 9 to 16 for E-9 to E-16), and its ports have no descriptions.
- **Marks:** walls, the stage, the network rack, exits, an extinguisher, first aid, the bar and the toilets,
  each on its layer.
- **Electrics:** two distribution boards with a circuit per seat row and one for the network rack.
- **Firewalls:** a `/28` per firewall, the next one as its backup.
- **Internet:** two lines on `core-01`, each with a host at the far end to measure latency.
- **Servers:** the LAN cache box `lancache-01`, which is also the hall's DNS server, and the provider's
  resolver for comparison; four game servers (two Counter-Strike 2, Minecraft, Trackmania), three of
  them with RCON. `CS2 #2` stops answering for two minutes in every five.
- **Internet sites:** the usual ones (Google, Steam, Discord...); Riot Games gets slow three minutes in ten.

The demo answers the DNS lookups, latency probes (also to the internet sites), game queries and RCON commands for its own servers
itself, so it sends nothing out. Try `status` on a Counter-Strike server or `list` on Minecraft in the
RCON console.

## Telemetry

The demo's switches and firewalls are in **Settings > Telemetry** the way you would set them up:
the core over SNMP, traps and gNMI, the Catalysts over SNMP and traps with their seat VLAN, the
firewalls with their own Telegraf. Every 30 seconds the demo hands the collector what Telegraf would
send for them: ports with traffic counters, the access switches' MAC tables, the core's ARP table,
LLDP neighbours, and the firewalls' CPU, memory, states and gateway. So the telemetry status, the
stored series and the endpoint search fill up like at an event. Nothing polls a device and no
Telegraf runs; the demo plugin stays the monitoring source.

## The event so far

The layout also leaves behind what a day of the event would, so no crew page starts empty. Each part is
only added while its page has nothing yet:

- **Crew:** three accounts without a password (`alex`, `sam`, `robin`) in the access, operations and
  electrics teams, so incidents have someone to be assigned to.
- **Incidents:** six of them, open, being worked and fixed, on seats, on `sw-c-02` and on a power circuit,
  with the crew's notes.
- **Check-ins:** most players checked in with their seat card's PIN over the last day. In the side hall
  the check-ins taught Floorbit most seats' ports (two are still unknown), and one PIN card was swapped,
  so the review tab has a port clash to look at. Two players moved seats during the night.
- **Status page:** two updates, with the public status page turned on.
- **Dashboards:** a "NOC wall" and an "Ops desk" layout.
- **Schedule:** the event from yesterday to tonight, with talks, meals, a tournament and quiet hours,
  shown on the public schedule.

Check-in is turned on as well, unless a setting already says otherwise.

## Language

Hall names, plan labels, incidents, status updates and the schedule are written in English.
Set `FLOORBIT_DEMO_LANGUAGE=de` before the demo is laid out to get them in Swiss German. What the demo
reports live (health tiles, findings) follows each viewer's language anyway.

Your own switches, seat blocks and hand entries stay as they are. To go back, turn the plugin off,
or unset `FLOORBIT_DEMO`. The demo devices stay in the inventory, marked as fed by the demo, until
you delete them.
