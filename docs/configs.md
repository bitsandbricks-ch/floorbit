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
tech's own switch username and password, used for that run and never stored. The command is
`show running-config` (`show configuration | display set` on Junos).

Backups run when someone presses the button. There are no nightly runs: those would need a switch
login kept on the server, and Floorbit keeps none. <!-- TODO: Mike decides whether a stored read-only service account is OK for nightly runs (issue #96). -->

## What is kept

- **Secrets are taken out first.** The values of `enable secret`, `username ... secret`, SNMP
  communities and users, TACACS+/RADIUS keys, key strings, pre-shared keys and Junos
  `encrypted-password` and `authentication-key` lines become `<removed>`. The copy on disk never had
  them.
- **Noise is left out.** "Last configuration change at", "Current configuration : n bytes", the
  NTP clock period and lines like them change without anyone changing anything.
- **Only changes are kept.** A backup that matches the switch's last copy only updates "Last backup".
- At most `CONFIG_KEEP` (50) copies per switch, in `configs/` next to `data.json`; the oldest go
  first, but never the baseline.

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

- `GET /api/configs`: every switch with its last copy, last backup and `changed`.
- `POST /api/configs/backup` with `{switches, username, password}`: `{results: [{switch, ok, error, copy, changed}]}`.
- `GET /api/configs/<switch>`: its copies, newest first, and the baseline.
- `GET /api/configs/<switch>/<id>`: one copy (`?download=1` as a file).
- `GET /api/configs/<switch>/diff?from=&to=`: unified diff lines, baseline to latest by default.
- `POST /api/configs/<switch>/baseline` with `{id}`.
