# Swapping a dead switch

When an access switch dies during the event, a block is offline until a spare is in. The
**Swap a switch** page (`/switch-swap/<switch id>`) walks the crew through it. **Problems** links it
from every offline switch, for anyone who may change the inventory (`floorplan.edit`).

## What stays and what changes

The switch keeps its **name and management IP**. A seat's port is the switch's name and the port
([seat mapping](seat-mapping.md)), so the seat mapping, the cables, the monitoring and the MAC
history carry on by themselves once the spare answers on the same IP. Only the hardware changes:
the serial number and the model.

## The steps

1. **Pick the spare.** The page lists the switches on the shelf: inventory switches with the
   status *In inventory*, the same model first. A spare that isn't in the inventory can be typed
   in by its serial number (and model, when it differs).
2. **Give it the config.** The page links the dead switch's last [config copy](configs.md) to
   paste into the spare before it is patched in. Only roles that may read configs
   (`configs.read`) see the link.
3. **Patch it back the same way.** The seats on this switch, by port: each cable goes back into
   the same port.
4. **Mark it swapped.** The switch takes the spare's serial number and model. The spare's
   inventory entry takes the dead box's serial number and model, with the status *Failed* and a note
   saying where it came from, so it is on the shelf for the return and nothing is deleted.

Each swap is kept on the switch (the last 20, shown under **Earlier swaps**), written to the
[audit log](audit.md) and added as a note to the switch's open [incident](incidents.md), so the
timeline and the report say when the new box went in.

The serial number and the model are then hand edits: a plugin that feeds the inventory (NetBox) no
longer overwrites them until someone unlocks them on the device page. Update the spare in NetBox
too, then unlock.

## API

`GET /api/switch-swap/<id>` returns the plan, `POST /api/switch-swap/<id>` with `{"spare_id": …}`
or `{"serial": …, "model": …}` records the swap. See the [API reference](api-reference.md).
