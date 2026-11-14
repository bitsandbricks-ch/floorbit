# Backup and restore

**Settings > Backup and restore** (admins only) saves and restores what takes work to set up.

## What a backup holds

| In a backup | Not in a backup |
| --- | --- |
| Manual switches, switch positions, the cached NetBox device list | API tokens, the Discord webhook and every other secret setting |
| Every hall with its background image, seat blocks and seats | Accounts and the session key |
| Saved settings, including the theme, event name and logo | Check-ins and their history (personal data) |

So a backup is safe to keep on a laptop or hand to the next event's orga team, and restoring one
never locks anybody out or overwrites a token.

## Restore

Pick a backup file. Settings shows what it holds and asks once. Restoring:

- replaces the floor plan with the backup's (halls and their background images, switches, positions,
  seat blocks); a part the backup doesn't have ends up empty, and a backup from before halls gives one hall;
- saves the backup's settings over the current ones; settings the backup doesn't name, and all
  secrets, keep their current value; settings this version doesn't know are skipped and listed;
- checks the whole file first: if anything is wrong, nothing changes.

Open editors and kiosk screens pick up the restored floor plan through live updates.

## Full copy

For a copy of everything, including accounts and tokens, back up the `data.json` file (and
`checkins.json` if check-in is on) while the app is stopped or idle.

## API

| Request | What it does |
| --- | --- |
| `GET /api/settings/backup` | Downloads `floorbit-backup-<date>.json`. |
| `POST /api/settings/backup` | Restores the JSON body. Answers with what was restored, or `400` and an error. |

The file is JSON: `{"format": "floorbit-backup", "version": 1, "created": ..., "layout": {...}, "settings": {...}}`.
