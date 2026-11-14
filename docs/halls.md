# Halls and floor plan import

An event can have more than one hall or floor. Each has its own floor plan: a background image,
switches and seat blocks. The editor shows one hall at a time.

## Halls

The hall picker in the editor's top bar switches between halls (the address gets `?hall=<id>`, and
the browser remembers the last one). The button next to it opens **Halls**:

- **Add hall**, rename one by editing its name.
- **Delete** a hall once it is empty: move or delete its switches and seat blocks first. The last
  hall always stays.
- **Background image** for each hall (below).
- **Import seat blocks (CSV)** into a hall (below).
- **Templates** opens the [template library](templates.md): save a hall or the whole plan, start from one.

An install from before halls is one hall called "Hall", holding everything. Nothing changes until
you add a second one.

A switch is placed in the hall shown when you place it; unplaced switches show in every hall's list.
Block names stay unique across halls, so seat numbers do too, and everything that works with seats
(seat mapping, stats, incidents, power, the seat finder) works the same with more than one hall.

## Background image

A PNG, JPEG, WebP or SVG of the hall plan, up to 5 MB, drawn faded under the switches and seats in
the editor and on the kiosk. It is stretched to the plan area, so an image with the hall's aspect ratio
lines up best; place a few seat blocks over it and adjust. Images are kept next to `data.json` in a
`halls/` folder, and backups carry them.

An uploaded SVG is served so it can't run script when opened on its own.

## Seat blocks from a CSV file

A header row, then one seat block per line, comma or semicolon separated:

```csv
name,x,y,cols,rows,rotation
A,20,25,12,2,0
B,60,25,12,2,0
C,20,60,12,2,90
```

| Column | Required | Meaning |
| --- | --- | --- |
| `name` | yes | The block's name; seat numbers are `<name>-<n>`. Unique across every hall. |
| `x`, `y` | yes | The block's centre, in percent of the plan (0 to 100). A decimal comma works. |
| `cols`, `rows` | yes | Seats per row and rows. |
| `rotation` | no | Degrees, 0 by default. |
| `seat_width`, `seat_height`, `spacing_x`, `spacing_y` | no | Sizes in percent of the plan, as in the editor. |
| `reverse_numbers` | no | `true` to number right to left. |

The import is all or nothing: if a line is wrong (a missing column, a number out of range, a name used
twice or already on the plan), nothing is added and the editor lists the lines to fix. At most 500 blocks
per file.

## Big screens and attendee pages

- `/kiosk?hall=<id>` shows another hall than the first; `/screen?hall=<id>` passes it on to its
  floor plan views. With more than one hall, the kiosk heading names the hall.
- The seat finder (`/find`) draws the hall the seat is in and names it.
- The attendee view (`/hall`) has a tab per hall.

## API

| Method and path | Needs | What |
| --- | --- | --- |
| `GET /api/halls` | `floorplan.view` | The halls in order: id, name, background URL, how many switches and seat blocks. |
| `POST /api/halls` `{"name"}` | `floorplan.edit` | Add a hall. |
| `PUT /api/halls/<id>` `{"name"}` | `floorplan.edit` | Rename. |
| `DELETE /api/halls/<id>` | `floorplan.edit` | Delete an empty hall (409 otherwise). |
| `GET /api/halls/<id>/background` | `floorplan.view` | The image. |
| `PUT /api/halls/<id>/background` `{"image": "data:image/png;base64,..."}` | `floorplan.edit` | Set it. |
| `DELETE /api/halls/<id>/background` | `floorplan.edit` | Remove it. |
| `POST /api/halls/<id>/seat-blocks.csv` | `floorplan.edit` | The CSV as `text/csv`, or `{"csv": "..."}`. 400 with `errors: [{line, error}]` if anything is wrong. |

`GET /api/switches` and `GET /api/seat-blocks` take `?hall=<id>`, and every switch and seat block
has a `hall_id`. `POST` and `PUT` on them take `hall_id` (the first hall when left out).
