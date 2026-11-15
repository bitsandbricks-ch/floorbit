# Teardown checklist

`/teardown` (Settings > Teardown) is the checklist for after the event. It shows what is done and
what is left, with a progress bar. Issue #37.

| Part | Done when |
|---|---|
| Gear back | nothing is checked out on the [gear page](gear.md). It lists who still has what. |
| Switch configs archived | every switch placed on the floor plan is ticked. Tick a switch once its config is saved (downloaded or pushed to NetBox). Until Floorbit can read configs from the switches itself (#96), a person ticks them. |
| Event data exported | the export was downloaded at least once |
| Our own steps | every step the team added is ticked ("return the rented switches", "power down hall 2") |

The **export** is one zip:

- `backup.json`: the same backup as Settings > Backup (the floor plan and settings, no secrets,
  no accounts);
- `report.pdf`: the [event report](report.md), without nicks or IPs;
- `incidents.csv`;
- `gear-history.csv`: every check-out and check-in;
- `handovers.json`: the [shift handovers](handover.md) and their notes.

Who can use it: leads and admins (`floorplan.edit`) see the checklist and tick it. Only admins
(`settings.manage`) download the export, because it holds a backup, the same as Settings > Backup.
Every tick, step and export goes to the audit log.

The checklist's state is kept in `data.json` under `teardown`.
