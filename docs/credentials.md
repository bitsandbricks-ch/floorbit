# Switch logins

**Settings > Switch logins** (`/settings/credentials`) keeps the switch logins that port actions
([ports.md](ports.md)), switch commands ([commands.md](commands.md)) and the terminal
([terminal.md](terminal.md)) use, so the crew doesn't type one for every action. Issue #474.

| Field | |
| --- | --- |
| For | `*` for every switch, a name pattern (`sw-a-*`, `core-?`) or one switch name. |
| Username | Shown in the list, so the crew can tell which login is set. |
| Password | Write-only: set or replace it, it never comes back out. |

The most specific login wins: the switch's own, then the longest pattern, then `*`. With a login for
`*`, the pages stop asking for one. A tech who types a login (through the API) still uses their own.
Without a login for `*`, the pages keep asking, and a switch command run uses the stored logins only
when every switch in it has one.

## How it is kept

- **Encrypted at rest** with AES-256-GCM. Each password has its own nonce and is bound to its login,
  so a value copied into another one doesn't open. Neither data.json nor the database ever holds it
  in clear, and backups don't include logins at all.
- **The key** lives in the file `FLOORBIT_SECRET_KEY_FILE` names (32 random bytes, base64):
  `head -c 32 /dev/urandom | base64 > secret.key`. In Kubernetes, mount it from a secret. Without that
  setting, Floorbit makes `secret.key` next to its data on first use (mode 0600). That still keeps the
  passwords out of backups and database dumps, but whoever has the whole state folder has the key too.
- **Opened only to use.** The password is decrypted for one SSH connection and dropped when it closes,
  like a typed one. Each use is in the audit log (**credentials**: "Used the stored login for sw-a-*",
  with the switch). So are setting and removing.
- **Who.** Setting and removing need `settings.manage` (admins). Using one needs what the action needs
  (`ports.act`, techs and up). A wrong stored password doesn't count toward a tech's login pause.

## A new key

1. Make the new key file and point `FLOORBIT_SECRET_KEY_FILE` at it.
2. Put the old one in `FLOORBIT_SECRET_OLD_KEY_FILES` (comma separated), so stored logins still open.
3. Run `python -m floorbit.vault rotate` in the container: every login is written again with the new key.
4. Remove `FLOORBIT_SECRET_OLD_KEY_FILES` and the old file.

A login made with a key Floorbit no longer has can't be opened: the action says so, and an admin sets
it again.

## API

- `GET /api/settings/credentials`: `{"credentials": [{"id", "kind", "scope", "username", "set_at", "set_by"}]}`.
- `PUT /api/settings/credentials/ssh`: `{"scope", "username", "password"}` sets or replaces the login for that scope.
- `DELETE /api/settings/credentials/<id>`.
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
