# Switches

**Network › Switches** (`/switches`, issue #902) is the inventory's switch list with what each switch
does right now. It is the first tab of the Network row, next to Firewalls and Wi-Fi.

## The figures

| Figure | What it counts |
| --- | --- |
| Switches up | Switches the status monitor reaches, of all switches; a down switch names how many seats lost their port |
| Ports up | Ports up on switches with seats |
| Busiest uplink | The uplink with the fullest direction, and where it goes |
| PoE in use | Watts drawn on all switches that report PoE, of their summed budget |

## The table

One row per switch in the inventory (role *switch*). A row opens the switch's page.

| Column | From |
| --- | --- |
| Tier | The topology: a switch others uplink to and without an uplink itself is *core*, one with seats or nothing below it *access*, the rest *distribution*. Empty without links. |
| State | The status monitor; *Uplink issue* when the uplink is down or slower than planned |
| Seats | The seat mapping (hand entries, cables, check-ins) and the port descriptions of the last read |
| Ports up | The last port read |
| Uplink, Last 24 h | The same columns as the inventory list ([Inventory](inventory.md)) |
| Uplink load | The busiest direction of the uplink port against its speed, from the last port read |
| PoE | Draw and budget from discovery's PoE action |

Filters: search, tier, state and hall. "Open in Inventory" opens the inventory filtered to switches.

The figures come from the inventory list (`GET /api/inventory`), which carries `seats`, `poe` and
`uplink.load` per device: no extra call per switch.
