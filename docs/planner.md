# Build planner

`/planner` (Settings > Build planner) helps plan the network before the event. Draw the hall in the
floor plan editor first. Floorbit then suggests the switches each seat block needs, the port each
seat gets, the VLANs and the management IPs. From that plan it makes the switch configs and
printable cable labels. Issue #34.

## The plan

| Setting | Default | |
|---|---|---|
| Switch model | Cisco IOS (Catalyst) | which config template and port names to use |
| Access ports per switch | 48 | |
| Uplink ports per switch | 2 | numbered on their own, e.g. `GigabitEthernet1/1/1` |
| Spare ports per switch | 2 | left free on every switch for crew, a stream PC or a swap |
| VLANs | one per seat block | or one per hall, or one for all seats |
| First seat VLAN | 100 | the next block gets 101, and so on |
| Switch names | `sw-{block}-{n:02d}` | `{block}` (lower case), `{hall}`, `{n}` |
| Management VLAN, network, first address, gateway | 10, empty, 11, empty | with a network, switches get addresses in order from the first host number |

Seats are taken row by row in the numbering the editor shows (rotation and reversed numbers
included). Each switch gets as many seats as it has access ports minus the spare ones. A block with
more seats gets more switches. The page warns when the management network is too small.

## Configs

Each switch model has a config template (Jinja) and port name patterns. Access ports use
`{n}`. Uplinks use `{u}` (the uplink's own number) or `{n}` (counted after the access ports).
Floorbit ships **Cisco IOS (Catalyst)** and **Aruba AOS-CX** templates. To change one, copy it on
the page and edit the copy.

A template gets:

- `switch`: `name`, `mgmt_ip`, `vlan`, `vlans`, `ports` (`name`, `seat`, `vlan`), `spare` and
  `uplinks` (`name`);
- `mgmt`: `vlan`, `netmask`, `prefix`, `gateway`;
- `vlans`: every seat VLAN;
- `event`: `name`.

Templates run in Jinja's sandbox, so a template can't reach Python objects or files. Every seat
port gets the description `Seat A-12`. That is the form the needs-attention watch, port actions
and the QoS hints read, so a switch built from the plan works with the rest of Floorbit with no
more setup.

The configs are a starting point. Read them before loading them onto a switch.

## Downloads

- **Configs (zip):** one `.cfg` per switch, plus `plan.csv`.
- **Port plan (CSV):** switch, port, seat, VLAN, block, hall and management IP for each seat.
- **Cable labels (PDF):** A4, 3 × 10 labels per page. Each label shows the seat in large type and
  the switch and port in small type. Print one or two per cable (two gives one for each end).
  `?block=A` prints one block only.

## Adding the switches

**Add switches to the floor plan** creates the planned switches that are not on the floor plan yet
(matched by name). They are placed next to their seat block, with status *planned*, the model and
the management IP. Existing switches are never changed.

Pushing the plan to NetBox is not built yet. Until it is, the CSV can be imported in NetBox.

## Who can use it

Accounts with **Edit the floor plan** (`floorplan.edit`), because the configs are the network's
design. Changes to the plan and the templates, and adding switches, go to the audit log.
