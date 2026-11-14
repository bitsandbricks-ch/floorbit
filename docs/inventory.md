# Inventory

The inventory is every switch, access point and other device Floorbit knows about. Floorbit owns
the list: it works with no plugin at all, filled by hand on the **Inventory** page (`/inventory`)
or by placing switches on the floor plan. Plugins such as NetBox add to it.

## What each device has

Name, role (switch, router, firewall, access point, server, other), model, serial, management IP,
hall or site, status and notes, plus where it sits on the floor plan. Every device on the floor
plan is an inventory device; unplaced ones wait in the floor plan's "add switch" dialog.

## How plugins feed it

A plugin with `uses: [inventory]` returns its devices when asked (**Sync now** on the Inventory
page, or the sync button on the floor plan). Floorbit merges them with these rules:

- **Hand edits win.** When you change a field a plugin also sends, the field is locked: syncs
  leave it alone. The Inventory page shows a lock and what the plugin says; **Use NetBox's value**
  unlocks it and takes the plugin's value again.
- **A sync never deletes.** A device a plugin stops sending is marked "Gone from NetBox" and stays.
- **Deleting a fed device hides it**, so the next sync doesn't bring it back. Turn on *Show hidden*
  to see it and show it again. Devices made by hand are really deleted.
- **First sync joins by name.** If a plugin sends a device whose name matches one made by hand,
  the two become one device. Fields that differed stay as you set them (locked).
- Every device remembers which plugins feed it and the last values each one sent.
- Every sync is logged: added, updated, joined, gone, and how many hand-edited fields it kept.
  The Inventory page shows the last sync per plugin; `GET /api/inventory/log` has the history.

Bad entries from a plugin (no ID, no name, an IP that isn't one) are skipped and counted, never
stored.

## Who may do what

Viewers and up see the inventory. Editors and up add, change, hide and sync. Changes are in the
audit log (area *inventory*), with field names, never values.

## API

| Request | What it does |
| --- | --- |
| `GET /api/inventory` | Devices (`?hidden=1` with hidden ones), the plugins that feed it and their last sync |
| `POST /api/inventory` | Add a device (`name` required) |
| `PATCH /api/inventory/<id>` | Change fields; `unlock: ["model"]` takes the plugin's value again; `hidden: false` shows it again |
| `DELETE /api/inventory/<id>` | Delete (made by hand) or hide (fed by a plugin) |
| `POST /api/inventory/sync` | Run every inventory plugin that's on |
| `GET /api/inventory/log` | The last 50 syncs (editors and up) |

The floor plan's `/api/switches` API works on the same list.

## Upgrading

The first time Floorbit reads `data.json` after the upgrade, it moves hand-placed switches and the
cached NetBox devices with their positions into the inventory, keeping their IDs. Backups made
before the upgrade still restore and are moved over the same way. Nothing to do by hand.
