# Cables and patching

`/cables` (Settings > Cables) records which switch port goes to which patch panel port and seat,
and prints a label for both ends of each cable. Issue #97.

A cable is **switch port → patch panel port → seat**. The panel and the seat are optional: a seat
patched straight into the switch has no panel, and an uplink has no seat.

| Field | |
| --- | --- |
| Switch, switch port | Needed. One cable per switch port: a second one is almost always a typo. |
| Patch panel, panel port | Optional. A panel port needs its panel. |
| Seat | Optional, written in capitals (`A-12`). |
| Label | Printed on both ends. Left empty, Floorbit numbers the cables `C-0001`, `C-0002`, ... Labels are unique. |
| Colour, length, note | Optional. The length is 0.1 to 500 metres. |

## Labels

**Print labels** makes an A4 PDF of 3 × 8 labels, two per cable: the switch end first, then the far
end (the seat, or the panel when there is no seat). Each label has:

- the cable's label, large;
- the end it goes on (`sw-a-01 Gi1/0/3` or `Seat A-3`), in bold;
- where the other end goes, small, and the colour and length;
- a QR code that opens the cable on this page (`/cables?cable=<id>`).

The PDF holds the cables the search shows. A cable's own window prints just its two labels. Behind a
reverse proxy, set `PUBLIC_URL` so the QR codes point at the address phones reach.

## From NetBox

When the NetBox plugin is set up, **Import from NetBox** reads `/api/dcim/cables/` and adds every
cable with a switch interface on one end:

- the interface's device and name become the switch and switch port;
- a front or rear port on the other end becomes the patch panel and panel port;
- the seat comes from the cable's description, written as `Seat: A-12` (NetBox has no seats);
- the cable's label, colour and length come along. A cable without a label is `NB-<NetBox id>`.

Each import replaces the last one, so NetBox stays the place to change these cables: they can't be
edited in Floorbit. Cables typed in Floorbit are kept, and one on the same switch port wins over
NetBox's, which is then skipped and counted in the import's message. If NetBox doesn't answer, the
last import stays.

Other inventory plugins can offer cables too, with a `cables()` method (see
[plugins.md](plugins.md)). The demo plugin has a cable for every demo seat.

## Who can do what

Everyone who can see the floor plan can see the cables and print labels. Adding, changing,
removing and importing need `floorplan.edit` (leads and admins). Each change is in the audit log
under **cables**, with the cable's label and route.

## API

- `GET /api/cables?q=&seat=&ids=`: the cables, and `sources`, the plugins that can import them.
- `POST /api/cables`, `PATCH /api/cables/<id>`, `DELETE /api/cables/<id>`.
- `POST /api/cables/import`: answers `{"imported", "errors"}`.
- `GET /api/cables/labels.pdf?q=&ids=`, `GET /api/cables.csv?q=`.

The feature can be turned off under Settings > Features (`cables`).
