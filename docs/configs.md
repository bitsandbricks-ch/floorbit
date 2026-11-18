# Switch configs

The **Switch configs** page (`/configs`) backs up the running config of the switches and shows what
changed during the event: which port someone shut, which VLAN someone added, compared with the
baseline from before doors opened. Open it from the Commands page.

Code: [`floorbit/config_backup.py`](../floorbit/config_backup.py),
[`floorbit/blueprints/configs.py`](../floorbit/blueprints/configs.py),
[`frontend/src/pages/Configs.tsx`](../frontend/src/pages/Configs.tsx).

## Backing up

Pick the switches (up to 20 at a time; **All** and **Without a copy** fill the list) and press
**Back up**. It uses the same plugin and the same login as [switch commands](commands.md): the
stored switch login when one covers every picked switch ([credentials.md](credentials.md)), else
the tech's own username and password, used for that run and never stored. The command is
`show running-config` (`show configuration | display set` on Junos).

## Every night

Every night at 04:00 server time Floorbit backs up each switch a stored switch login covers, so the
copies are there even when nobody pressed the button. A read-only switch account is enough. The
page says how many switches the run covers and how the last one went, and the audit log has one
line per run, by "nightly backup". Switches without a stored login are left out; store one in the
[inventory](inventory.md#credentials) (an SSH credential on All devices, a group, a tag or the switch).

- `CONFIG_BACKUP_HOUR`: the hour (0 to 23, server time) it runs, `4` by default. `off` turns the
  nightly run off.
- With several pods, only the leader runs it ([kubernetes.md](kubernetes.md)).

## What is kept

- **Secrets are taken out first.** The values of `enable secret`, `username ... secret`, SNMP
  communities and users, TACACS+/RADIUS keys, key strings, pre-shared keys and Junos
  `encrypted-password` and `authentication-key` lines become `<removed>`. The copy on disk never had
  them.
- **Noise is left out.** "Last configuration change at", "Current configuration : n bytes", the
  NTP clock period and lines like them change without anyone changing anything.
- **Only changes are kept.** A backup that matches the switch's last copy only updates "Last backup".
- At most `CONFIG_KEEP` (50) copies per switch, in the database ([database.md](database.md));
  the oldest go first, but never the baseline.

## Baseline and diff

The first copy of a switch is its **baseline**: the overview says whether the switch changed since.
Mark another copy as the baseline when the build is done and the event starts. Click a switch to
see its copies and the diff from the baseline to the latest copy; **Compare** shows any copy
against the baseline, and each copy can be downloaded.

## Who

Everything here needs `configs.read`: admins and leads by default. A config describes the whole
network, even without its secrets. Every backup is in the [audit log](audit.md), per switch, with
"(changed)" when it kept a new copy, and so is a new baseline.

## API

- `GET /api/configs`: every switch with its last copy, last backup and `changed`, and `nightly`
  (`hour`, `covered`, `switches`, `last`).
- `POST /api/configs/backup` with `{switches, username, password}`: `{results: [{switch, ok, error, copy, changed}]}`.
- `GET /api/configs/<switch>`: its copies, newest first, and the baseline.
- `GET /api/configs/<switch>/<id>`: one copy (`?download=1` as a file).
- `GET /api/configs/<switch>/diff?from=&to=`: unified diff lines, baseline to latest by default.
- `POST /api/configs/<switch>/baseline` with `{id}`.
