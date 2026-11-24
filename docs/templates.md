# Floor plan templates

**Templates** (`/templates`, linked from Settings and the editor's **Plan** menu) keeps floor plans
to start from later: the layout of last year's event, or one another LAN shared.

## What a template holds

The floor plan as it was saved, of every hall or of one:

- the halls with their names and background images, where each image sits and the hall's scale
  ([halls.md](halls.md));
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

## In the editor

The **Plan ▾** menu in the editor's top bar works on the plan as a whole:

- **Save as template…** saves the hall on screen (or, picked in the dialog, every hall) to the library.
- **Start from a template…** lists the library; picking one asks for the version and, for a one-hall
  template, which hall it goes into (the one on screen at first), then replaces it. The undo history
  starts over.
- **Place a preset…** puts a saved preset on the plan (below).
- **Versions of this hall…** and **Halls…** open the dialogs below and in [halls.md](halls.md).
- **Template library** opens this page.

A hall with nothing on it yet offers **Start from a template** in the editor's panel.

## Presets

A template is a whole plan; a **preset** is a piece of one to place again, any number of times: an
admin zone with its seat blocks, walls and labels, a U of tables, a stage with its marks.

- Select the items, right-click and pick **Save as preset…**, and give it a name. Seat blocks (with
  their rows), walls, zones, text, icons, patch panels and power boards go in; switches and cables
  don't (a switch is one device, a switch port has one cable).
- **Plan ▾ → Place a preset…**, or right-click an empty spot and **Place a preset…**, lists them with
  what each holds. **Place** puts it where you right-clicked or where the pointer last was, like a
  paste: seat blocks get the next free row letters or block names, panels and boards the next free
  names, and the new items are selected so you can move them. Undo takes them away again.
- The bin deletes a preset; what was placed from it stays.

Presets belong to the whole installation (or tenant), not one event, in `plan-presets.json` next to the
templates.

**Versions of this hall** is a shortcut for one hall: **Save this version** keeps
the hall as it is now under a name (the hall and the time if none is given), and **Restore** puts a
saved one back into the hall, first saving the plan as it was ("Before restoring …") unless that box
is unticked. The undo history starts over after a restore. Versions are templates of one hall, so
they show here too.

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
