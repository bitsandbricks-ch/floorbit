# Shift handover

`/handover` (linked from the incident board) shows the outgoing shift what happened since the
last handover. It also gives them a place to leave a note for the next shift. Issue #33.

## What it shows

- **The last shift's note**, who wrote it and when.
- **Figures:** incidents open, new this shift, fixed this shift, switch outages, problems right
  now and changes. Under incidents open it says how many have waited 10 minutes or more with
  nobody on them, and under fixed this shift how fast: **half within 14 min** (the median from
  filed to fixed, so one long job doesn't skew it). The copied text and the Discord post say both too.
- **Still open:** every incident not fixed yet. Those on [match seats](tournament.md) are listed
  first, then open before taken, oldest first. One nobody has taken for 10 minutes has the
  board's **Waiting 25 min** tag.
- **Fixed this shift**, with who fixed how many: **By: kim 4 · ana 2 · nobody named 1** (in the copied text too).
- **Switch outages** since the last handover, how long they lasted, and those still down.
- **Changes from the [audit log](audit.md):** port actions, settings, the floor plan, power,
  plugins, accounts, security and check-ins. Incidents have their own sections, and sign-ins are
  left out.
- **Seat notes from this shift:** the [crew notes on seats](seats.md#the-inspector) written or changed since the
  last handover, newest first, each linking to its seat. Only shown when there are some; they are
  not posted to Discord.
- **Muted right now:** every switch and service whose [alerts are muted](alerts.md#muting-a-switch-or-a-service),
  until when, by whom and why, so a mute set by the last shift is not forgotten. The
  [crew notice](crew-notice.md) that is up is shown at the top.
- **Gear still out:** who holds [gear](gear.md) and which pieces, most first; each name opens the
  gear page on that person's pieces. Only shown when something is out and the gear page is on.

The first summary looks back 8 hours. After that, each summary starts where the last handover
ended.

## Handing over

Write the note and press **Hand over**. The handover is saved with its figures (the newest 100 are
kept in `data.json` under `handover`). The next summary starts from that moment, and the handover
is written to the audit log. With Discord alerts or the [crew channel](crew-discord.md) set up,
**Also post the summary to Discord** posts the figures, what is muted, who still has gear, the five oldest open
incidents and the note. The message mentions nobody.

**Copy as text** at the top puts the summary on the clipboard as plain text, for a crew that hands
over in another chat or by mail: the figures, every open incident, those fixed this shift, the
switch outages, the crew notice, what is muted, the gear still out and the note as written so far. Changes and seat notes stay on the page.

## Who can use it

Accounts with **Work incidents** (`incidents.work`): techs, leads and admins. The summary names
people from the audit log, so viewers and kiosks don't see it.

## API

- `GET /api/handover`: the summary since the last handover, the last 10 handovers, and whether
  Discord is set up.
- `POST /api/handover` `{"note": "...", "discord": true}`: hand over.
