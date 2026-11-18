# Backup and restore

**Settings > Backup and restore** (admins only) saves and restores what takes work to set up.

## What a backup holds

| In a backup | Not in a backup |
| --- | --- |
| Manual switches, switch positions, the cached NetBox device list | API tokens, the Discord webhook and every other secret setting |
| Every hall with its background image, seat blocks and seats | Accounts and the session key |
| Cables, their drawn routes, patch panels, uplinks between switches and port areas | Check-ins and their history (personal data) |
| Power boards and circuits (not which circuit is marked tripped, nor the last readings) | Live state: port status, meter readings, incidents |
| Saved settings, including the theme, event name and logo | |

So a backup is safe to keep on a laptop or hand to the next event's orga team, and restoring one
never locks anybody out or overwrites a token.

## Restore

Pick a backup file. Settings shows what it holds and asks once. Restoring:

- replaces the floor plan with the backup's (halls and their background images, switches, positions,
  seat blocks); a part the backup doesn't have ends up empty, and a backup from before halls gives one hall;
- replaces the cabling and power as a whole: cables, routes, patch panels, uplinks, port areas,
  boards and circuits added after the backup are gone afterwards. A backup from a version before
  these were in it has none of them: they are left as they are, and Settings says so;
- saves the backup's settings over the current ones; settings the backup doesn't name, and all
  secrets, keep their current value; settings this version doesn't know are skipped and listed;
- checks the whole file first, every seat block, plan mark, cable, patch panel, uplink, port area and
  power circuit with the same rules as the editor, against the floor plan being restored (an uplink
  to a switch the backup doesn't have is refused): if anything is wrong, nothing changes, and the
  error names the entry.

Open editors and kiosk screens pick up the restored floor plan through live updates.

## Full copy

For a copy of everything, including accounts and tokens, back up the `data.json` file (and
`checkins.json` if check-in is on) while the app is stopped or idle.

## API

| Request | What it does |
| --- | --- |
| `GET /api/settings/backup` | Downloads `floorbit-backup-<date>.json`. |
| `POST /api/settings/backup` | Restores the JSON body. Answers with what was restored (`kept` lists the cabling and power parts an older backup left as they were), or `400` and an error. |

The file is JSON: `{"format": "floorbit-backup", "version": 1, "created": ..., "layout": {...}, "settings": {...}}`.
