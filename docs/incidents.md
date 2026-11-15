# Incidents and the seat helpdesk

Problems during the event, tied to a seat, a switch or a power circuit ([power.md](power.md)), on the **Incidents** board (`/incidents`).
Code: [`floorbit/incidents.py`](../floorbit/incidents.py) and
[`floorbit/blueprints/incidents.py`](../floorbit/blueprints/incidents.py).

## The board

Three columns: **Open**, **Being worked** and **Fixed**. Each incident shows where it is, its team,
who has it, its notes and, for reports from a seat, what the network said about that seat's port.
The board refreshes on its own and as soon as anything changes. Open incidents also show on the
floor plan as a red ring on the seat or switch, with a count next to **Incidents** in the top bar.
The board's browser tab starts with the number of open incidents, e.g. "(2) Incidents · Floorbit".
An open incident that nobody has taken for 10 minutes gets an orange **Waiting 25 min** tag, so the
ones that slipped through stand out. They move to the top of the **Open** column, the one waiting
longest first; the rest stay newest first. A seat with more than one incident on the board says so on each later one, e.g. **Incident no. 3
at this seat**: a seat that keeps coming back often has a cable or port to check. The badge opens
the board on every incident at that seat (`seat:D-6`), fixed ones too, to see what was tried. **Take the next one** gives you the oldest open incident
nobody has that you may work, and says which one it was; the **n** key does the same (not while
you type in a field). The [event report](report.md) shows how long incidents waited
on average.

**Filter** narrows the columns to incidents whose title, seat, switch, circuit, assignee, team or
notes contain the text, ignoring case. `seat:D-2` matches that seat only (not D-20), `switch:sw-a-01` one switch by name or id (not sw-a-010), and `with:kim` the incidents kim is on (not those that only mention kim in a note). It is kept in the address (`/incidents?q=B-7`), so a link can
open the board filtered, and it works together with **Only what I can work**. **/** anywhere on the
board puts the cursor in it, as on the [Seats page](seats.md#keyboard-and-screen-readers).

A fixed incident says how long it took from filed to fixed, e.g. **With kim · fixed after 12 min**
(or **Fixed after 1 h 5 min** when nobody was named on it).

An open incident whose seat is on a switch that is down right now gets a red tag, e.g.
**sw-c-02 down · 5 min ago**: likely part of that outage rather than the seat's cable. The seat's
switch comes from the last port read or the status page's memory; no tag when it isn't known.

An incident on a seat that has a [crew note](seats.md#the-inspector) shows the note on its card,
with who wrote it and when, so whoever takes it knows what was already done there.

**New incident** warns when the seat or switch you pick already has incidents that are not fixed
(**Already open here**), with their titles, status and who has them, so two techs don't file the
same broken seat twice. You can still file it.

The seat or switch badge on a card opens it on the [Seats page](seats.md) (`/plan?seat=D-6`,
`/plan?switch=sw-a-01`), in the hall it is in.

Who can do what (permissions in [auth.md](auth.md)):

| Action | Needs |
| --- | --- |
| See the board | `incidents.work` in the account's role or in a team role |
| Take, fix, reopen, add a note | `incidents.work` in the incident's team, through a membership of that team or one above it. Incidents without a team need it in the account's role. |
| Give it to someone else, move it to another team | `incidents.assign` (in the role, or as a team role in both teams) |
| File an incident | `incidents.work` for the team it goes to |
| Print the seat QR codes | `incidents.assign` |

Someone can only be given an incident they could work themselves. Moving an incident to a team its
assignee doesn't work for puts it back to open.

## The helpdesk on each seat

**Incidents › Seat QR codes** (`/incidents/qr`) prints one QR code per seat, for every seat on the
floor plan. To replace a torn sticker or reprint one block, pick a **Block** or type the seats under
**Only these seats** (`D-6, D-7`): **Print** prints only the codes shown. On the [Seats page](seats.md),
the seat inspector's **QR code** and the block panel's **Print QR codes** open the sheet that way
(`/incidents/qr?seats=D-6`, `/incidents/qr?block=D`). Scanning one opens `/help/<seat>`: a small page, in English or German after the phone's
language, with four buttons (no internet, slow connection, no power, something else), and a
[speed test](speedtest.md) whose result goes with the report.

- **No account, nothing personal:** the page asks for no name or text.
- **Only printed codes work:** each link carries a signature made with the app's `SECRET_KEY`, so
  nobody can report for seats by typing URLs. Changing `SECRET_KEY` means printing new codes.
- **Rate limited:** 5 reports per client IP per 10 minutes.
- **No duplicates:** a second report of the same problem at the same seat counts up ("2 reports")
  on the open incident instead of filing another one.
- **Where it stands:** opening the page again shows the seat's latest report: nobody has taken it
  yet, it was [sent to a tech](dispatch.md) who hasn't said "On my way" yet, someone from the team
  has it and is on the way, or it was marked fixed (for half an hour after the fix). It never says who.
  While nobody has it, it also says how many open reports nobody has taken were filed before it
  ("3 reports are ahead of yours"), across the whole board: only the number.
- **Known outage:** when the switch serving the seat is down according to the status monitor, the
  page opens with "We know: the network at your seat has been down for 12 min. The team is on it,
  no need to report it." The buttons stay for anything else. The seat's switch comes from the last
  port read or from what the [status page](status-page.md) remembered; a seat with no known port
  gets no message. No switch names. When the status page is public, the note links to it for the
  crew's updates.
- **It works again:** while the seat has an open report, the page has an **It works again** button
  for problems that fixed themselves. It tags the seat's open reports on the board (**Seat says it
  works again · 3 min ago**) but doesn't mark them fixed: the link is anonymous, so the crew checks
  or asks first. Reporting again clears the tag. Rate limited like reports. A report the seat called
  off doesn't count as waiting (no **Waiting** tag, not in the handover's or dashboard's waiting
  count), and **Take the next one** takes it last.
- **Located and checked:** the incident arrives with the seat, and with the switch, port, link
  state and whether a device is seen on the port, looked up through the monitoring source when it
  is reported. No IP, MAC or nick is stored with it.

Reports go to a team by problem, if that team exists: no internet and slow → Access, no power →
Electrics, something else → Operations. Otherwise they wait without a team for someone with
`incidents.assign`. (Routing rules per area come with issue #11.)

Set **Public URL** (Settings › General, `PUBLIC_URL`) when Floorbit runs behind a reverse proxy, so the QR codes point
at the address attendees can reach.

Every change (filed, changed, reported from a seat, "works again" from a seat) goes to the audit log under **Incidents**.

To send incidents to the nearest free tech and work them from a phone, see [dispatch](dispatch.md).
