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

## Backups in an S3 bucket

Floorbit can keep the same backup in an S3 bucket: Amazon S3, or any store that speaks its API
(MinIO, Garage, Backblaze B2, Wasabi, Ceph). Set it up on **Settings > Backups to S3**, or with
environment variables (a value saved on the page wins over the variable):

| Setting | Variable | Default |
| --- | --- | --- |
| S3 endpoint | `S3_BACKUP_ENDPOINT` | empty: Amazon S3 (`https://<bucket>.s3.<region>.amazonaws.com`). For other stores their URL, like `https://s3.example.com`; the bucket then goes in the path. |
| Region | `S3_BACKUP_REGION` | `us-east-1` |
| Bucket | `S3_BACKUP_BUCKET` | empty: S3 backups are off |
| Folder in the bucket | `S3_BACKUP_PREFIX` | `floorbit/` |
| Access key ID, secret access key | `S3_BACKUP_ACCESS_KEY`, `S3_BACKUP_SECRET_KEY` | |
| Encryption passphrase | `S3_BACKUP_PASSPHRASE` | empty: not encrypted |
| Back up every (hours) | `S3_BACKUP_INTERVAL_HOURS` | `24`; `0` only uploads when someone presses **Back up now** |
| Backups kept | `S3_BACKUP_KEEP` | `30` |

- **What goes up** is the backup described above (floor plan, cabling, power, settings; no secrets,
  accounts or check-ins), gzipped, as `floorbit-backup-<date>-<time>Z.json.gz` in the folder.
- **Tenants.** On a platform with several tenants sharing one bucket, each keeps its backups in
  its own folder below the one set here (`<folder>tenants/<id>/`); the default tenant uses the
  folder itself. None lists, prunes or restores another's (docs/tenancy.md).
- **Encryption.** With a passphrase, each file is encrypted on the Floorbit server before it is
  uploaded (AES-256-GCM, the key made from the passphrase with scrypt) and ends in `.enc`. Whoever
  owns the bucket can't read it. Keep the passphrase somewhere else too: without it nobody can
  restore an encrypted backup.
- **Secrets.** The access keys and the passphrase are stored encrypted like every secret setting
  ([credentials](credentials.md)), are never shown again, and are never in a backup. Changing them is
  in the audit log, as are uploads, restores and downloads.
- **Schedule.** One backup every `S3_BACKUP_INTERVAL_HOURS`, counted from the last one. A failed
  upload is tried again after 15 minutes and shows on the Settings page. With several pods only the
  leader uploads.
- **Retention.** After each upload, only the newest `S3_BACKUP_KEEP` backups in the folder stay.
  Other files in the folder are never listed or deleted. A bucket lifecycle rule or object lock on
  top is fine.
- **Restore.** **Settings > Backup and restore** lists the backups in the bucket. **Restore** works
  like restoring a file (see above); **Download** gives the opened JSON file. A new install restores
  one by setting the same bucket, keys and passphrase.
- **Key rights.** The key needs `s3:ListBucket` on the bucket and `s3:PutObject`, `s3:GetObject` and
  `s3:DeleteObject` on the folder; nothing else.

To open a downloaded `.enc` file without a running Floorbit:

```sh
S3_BACKUP_PASSPHRASE=... python -m floorbit.s3_backup decrypt floorbit-backup-20261118-040000Z.json.gz.enc
```

It writes the JSON file next to it (asks for the passphrase when the variable isn't set).

| Request | What it does |
| --- | --- |
| `GET /api/settings/backup/s3` | The schedule, the last run and the backups in the bucket. |
| `POST /api/settings/backup/s3` | Uploads a backup now. |
| `POST /api/settings/backup/s3/restore` | Restores `{"key": ...}`, one of the listed backups. |
| `GET /api/settings/backup/s3/download?key=...` | One listed backup as the JSON file. |

## Full copy

For a copy of everything, including accounts and tokens, back up the `data.json` file (and
`checkins.json` if check-in is on) while the app is stopped or idle.

## API

| Request | What it does |
| --- | --- |
| `GET /api/settings/backup` | Downloads `floorbit-backup-<date>.json`. |
| `POST /api/settings/backup` | Restores the JSON body. Answers with what was restored (`kept` lists the cabling and power parts an older backup left as they were), or `400` and an error. |

The file is JSON: `{"format": "floorbit-backup", "version": 1, "created": ..., "layout": {...}, "settings": {...}}`.
