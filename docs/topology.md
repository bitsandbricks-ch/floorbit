# Topology

**Network › Topology** (`/topology`) draws the links between switches: the uplinks from the access
switches to distribution, from there to the core, and to the routers and firewalls. Each link has
its cable type and planned speed, and Floorbit checks it against what the switches report.

## Links

A link joins a port on one switch with a port on another. Leads and admins (`floorplan.edit`) press
**Add link** and give:

| Field | What |
| --- | --- |
| From switch, port | One end, for example `sw-a-01` `Te1/1/1`. Switches come from the [inventory](inventory.md). |
| To switch, port there | The other end, for example `dist-01` `Te1/0/1`. |
| Type | Copper Cat5e, Cat6 or Cat6a, fiber single-mode or multi-mode, or DAC. Optional. |
| Speed | 1, 10, 25, 40 or 100G: what the link should run at. Optional. |
| Note | Anything the crew should know, like the patch panel it runs through. |

A port belongs to one link at most; `Te1/1/1` and `TenGigabitEthernet1/1/1` count as the same port.

## What the page shows

- **The diagram**, from the top of the network down: routers and firewalls first (or the switch with
  the most links), then what hangs off them. A wide layer wraps into rows. The colour is the cable type
  (blue copper, yellow single-mode, cyan multi-mode, violet DAC); a thicker line is a faster link.
- **Down** (red, dashed): the port at either end reports it down.
- **Slower than planned** (orange): the port is up at less than the planned speed. A 10G uplink that came up
  at 1G usually means a wrong optic or a bad cable.
- Pick a switch or a link to see its details on the side (at the bottom on a phone).

The state comes from the monitoring source's port list (`device_ports`, the same as the needs-attention
watch), read at most every 30 seconds per switch. A link whose switches can't be read is *not read*.

## On the floor plan

Links between two switches that are both placed on a hall's plan are drawn there as lines between them,
in the same colours and widths, under the switches. A link last seen down is red and
dashed, one slower than planned orange. The floor plan doesn't read the switches itself: Floorbit reads
the ports at both ends of every link in the background every 30 seconds, and the plan and the
Problems page show that. A link that is down or slow is also listed on the Problems page.

## Seen by LLDP

When the monitoring source can tell what each switch sees on its ports by LLDP or CDP (LibreNMS can,
through its links), the page lists the neighbours that no link explains yet. **Add** opens the form
with both ends filled in, and the speed the port runs at. The plan stays the crew's: nothing is added
on its own.

A plugin offers this with an optional `neighbours(hostname)` returning
`[{"port", "remote", "remote_port", "protocol"}]`. With a [local agent](agent.md), the agent answers it.

## API

- `GET /api/links`: `{"nodes", "links", "suggestions", "counts", "types", "speeds"}`. Each link has `id`,
  `a`, `a_port`, `b`, `b_port`, `type`, `speed`, `note`, `media`, and its live `state` (`up`, `down`, `unknown`),
  `speed_bps` and `issue` (`down`, `slow` or empty).
- `POST /api/links`, `PUT /api/links/<id>`, `DELETE /api/links/<id>` (`floorplan.edit`), audit-logged.
