# Switch logins

The switch logins that port actions ([ports.md](ports.md)), switch commands ([commands.md](commands.md)),
the terminal ([terminal.md](terminal.md)) and config backups ([configs.md](configs.md)) use are the
**inventory's SSH credentials** ([inventory.md](inventory.md#groups-and-tags)), so the crew doesn't type
one for every action. Issue #474.

Set one on **All devices** (every switch), on a group or a tag, or on one device. The most specific
one wins: the device's own, then its tags, its group and the group's parents, then All devices. With
an SSH credential on All devices, the pages stop asking for a login. A tech who types a login
(through the API) still uses their own. Without one there, the pages keep asking, and a switch
command run uses the stored logins only when every switch in it has one. A switch that isn't in the
inventory has no stored login.

**Settings > Switch logins**, the older page with logins by name pattern, is gone: Floorbit moved its
logins into the inventory once (`floorbit/upgrades.py`). A login for `*` went on All devices, one for
a single switch name on that device, and a pattern such as `sw-a-*` on a tag of that name, given to
every device it matched then. A switch added later gets the tag in the inventory, not by its name.
Old links to `/settings/credentials` open the inventory.

## How it is kept

- **Encrypted at rest** with AES-256-GCM. Each password has its own nonce and is bound to its login,
  so a value copied into another one doesn't open. Neither data.json nor the database ever holds it
  in clear, and backups don't include logins at all.
- **The key** lives in the file `FLOORBIT_SECRET_KEY_FILE` names (32 random bytes, base64):
  `head -c 32 /dev/urandom | base64 > secret.key`. In Kubernetes, mount it from a secret. Without that
  setting, Floorbit makes `secret.key` next to its data on first use (mode 0600). That still keeps the
  passwords out of backups and database dumps, but whoever has the whole state folder has the key too.
- **Opened only to use.** The password is decrypted for one SSH connection and dropped when it closes,
  like a typed one. Each use is in the audit log (**credentials**: "Used the stored ssh login set on
  tag sw-a-*", with the switch). So are setting and removing.
- **Who.** Setting and removing are for admins. Using one needs what the action needs
  (`ports.act`, techs and up). A wrong stored password doesn't count toward a tech's login pause.

## A new key

1. Make the new key file and point `FLOORBIT_SECRET_KEY_FILE` at it.
2. Put the old one in `FLOORBIT_SECRET_OLD_KEY_FILES` (comma separated), so stored logins still open.
3. Run `python -m floorbit.vault rotate` in the container: every login is written again with the new key.
4. Remove `FLOORBIT_SECRET_OLD_KEY_FILES` and the old file.

A login made with a key Floorbit no longer has can't be opened: the action says so, and an admin sets
it again.

## API

- `GET /api/inventory/credentials`, `PUT /api/inventory/credentials`
  (`{"owner_type": "defaults" | "group" | "tag" | "device", "owner_id", "kind": "ssh", "username", "secret"}`)
  and `DELETE /api/inventory/credentials/<id>`: see [inventory.md](inventory.md).
- `GET /api/ports` says `stored_login` when any login is stored, and `needs_login` is false once one covers every switch.

RCON passwords for [game servers](game-servers.md) are kept the same way, and `rotate` moves them too.

## Secret settings

Every setting of the secret kind is kept the same way: the NetBox and LibreNMS API tokens, sign-in
client secrets, and every plugin's secret settings. Each one is sealed for its own setting, so a
sealed token copied into another setting doesn't open there. A value saved before this release
keeps working, and it is sealed the next time any setting is saved. `rotate` moves these values to
the new key too.

When a saved secret doesn't open (for example, the key file changed), Floorbit treats it as not
set. The settings page says *Saved, but it doesn't open with the current secret key* until someone
enters the value again. A value set through an environment variable is never stored, so none of
this applies to it.
