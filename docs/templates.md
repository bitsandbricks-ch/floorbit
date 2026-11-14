# Floor plan templates

**Templates** (`/templates`, linked from Settings and the editor's Halls dialog) keeps floor plans
to start from later: the layout of last year's event, or one another LAN shared.

## What a template holds

The floor plan as it was saved, of every hall or of one:

- the halls with their names and background images ([halls.md](halls.md));
- where the switches are (name, role, model, position, hall);
- the seat blocks.

Never event data: no check-ins, nicks, IPs (also no switch management IPs), MACs, serials, notes,
secrets or accounts. A template only ever copies the fields listed above, and an imported file is cut
down to them; the page says which fields it took out.

## The library

- **Save floor plan as template:** a name, a description, and every hall or just one.
- **Save again** adds the floor plan as it is now as the newest version; the last 10 versions are kept,
  and each can be downloaded or started from.
- **Rename**, **Duplicate** (the newest version) and **Delete**.
- **Download** gives a `.json` file to keep or share; **Import file** adds one to the library.

Templates are files in `layout-templates/` next to `data.json` (with Compose, in the state volume).
They are not in [backups](backup.md); download the ones to keep.

## Starting from a template

**Start from this** replaces the floor plan after one confirmation, like restoring a backup, and goes
to the audit log:

- A template of every hall replaces all halls, background images and seat blocks.
- A template of one hall can go into one hall instead, leaving the others as they are. Its block names
  must not be used in another hall (seat numbers stay unique).
- Switches are matched to the inventory by name: a known one is placed where the template has it
  and keeps its own data (NetBox, management IP); an unknown one is added by hand. Switches the
  template doesn't have are taken off the plan, not deleted.

The seat mapping, check-ins and incidents are not touched.

## API

Reading needs `floorplan.view`, everything else `floorplan.edit`.

| Method and path | What |
| --- | --- |
| `GET /api/templates` | The library: names, descriptions, versions with what each holds. |
| `POST /api/templates` `{name, description, hall?}` | Save the floor plan (or one hall) as a template. |
| `PATCH /api/templates/<id>` `{name?, description?}` | Rename or describe. |
| `DELETE /api/templates/<id>` | Delete with every version. |
| `POST /api/templates/<id>/versions` `{hall?}` | Save the floor plan again as the newest version. |
| `POST /api/templates/<id>/duplicate` | A copy of the newest version. |
| `GET /api/templates/<id>/export?version=` | The file (`{"format": "floorbit-template", "version": 1, ...}`). |
| `POST /api/templates/import` | Add a file to the library; the answer lists `dropped` fields. |
| `POST /api/templates/<id>/apply` `{version?, hall?}` | Start from it. |
