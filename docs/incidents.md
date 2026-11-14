# Incidents and the seat helpdesk

Problems during the event, tied to a seat or a switch, on the **Incidents** board (`/incidents`).
Code: [`floorbit/incidents.py`](../floorbit/incidents.py) and
[`floorbit/blueprints/incidents.py`](../floorbit/blueprints/incidents.py).

## The board

Three columns: **Open**, **Being worked** and **Fixed**. Each incident shows where it is, its team,
who has it, its notes and, for reports from a seat, what the network said about that seat's port.
The board refreshes on its own and as soon as anything changes. Open incidents also show on the
floor plan as a red ring on the seat or switch, with a count next to **Incidents** in the top bar.

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
floor plan. Scanning one opens `/help/<seat>`: a small page, in English or German after the phone's
language, with four buttons (no internet, slow connection, no power, something else).

- **No account, nothing personal:** the page asks for no name or text.
- **Only printed codes work:** each link carries a signature made with the app's `SECRET_KEY`, so
  nobody can report for seats by typing URLs. Changing `SECRET_KEY` means printing new codes.
- **Rate limited:** 5 reports per client IP per 10 minutes.
- **No duplicates:** a second report of the same problem at the same seat counts up ("2 reports")
  on the open incident instead of filing another one.
- **Located and checked:** the incident arrives with the seat, and with the switch, port, link
  state and whether a device is seen on the port, looked up through the monitoring source when it
  is reported. No IP, MAC or nick is stored with it.

Reports go to a team by problem, if that team exists: no internet and slow → Access, no power →
Electrics, something else → Operations. Otherwise they wait without a team for someone with
`incidents.assign`. (Routing rules per area come with issue #11.)

Set **Public URL** (Settings › General, `PUBLIC_URL`) when Floorbit runs behind a reverse proxy, so the QR codes point
at the address attendees can reach.

Every change (filed, changed, reported from a seat) goes to the audit log under **Incidents**.
