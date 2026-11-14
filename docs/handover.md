# Shift handover

`/handover` (linked from the incident board) shows the outgoing shift what happened since the
last handover. It also gives them a place to leave a note for the next shift. Issue #33.

## What it shows

- **The last shift's note**, who wrote it and when.
- **Figures:** incidents open, new this shift, fixed this shift, switch outages, problems right
  now and changes.
- **Still open:** every incident not fixed yet. Those on [match seats](tournament.md) are listed
  first, then open before taken, oldest first.
- **Fixed this shift.**
- **Switch outages** since the last handover, how long they lasted, and those still down.
- **Changes from the [audit log](audit.md):** port actions, settings, the floor plan, power,
  plugins, accounts, security and check-ins. Incidents have their own sections, and sign-ins are
  left out.

The first summary looks back 8 hours. After that, each summary starts where the last handover
ended.

## Handing over

Write the note and press **Hand over**. The handover is saved with its figures (the newest 100 are
kept in `data.json` under `handover`). The next summary starts from that moment, and the handover
is written to the audit log. With Discord alerts or the [crew channel](crew-discord.md) set up,
**Also post the summary to Discord** posts the figures, the five oldest open incidents and the
note. The message mentions nobody.

## Who can use it

Accounts with **Work incidents** (`incidents.work`): techs, leads and admins. The summary names
people from the audit log, so viewers and kiosks don't see it.

## API

- `GET /api/handover`: the summary since the last handover, the last 10 handovers, and whether
  Discord is set up.
- `POST /api/handover` `{"note": "...", "discord": true}`: hand over.
