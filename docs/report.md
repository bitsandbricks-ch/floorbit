# Post-event report

**Event report** (`/report`, linked from the stats page) sums the event up in numbers, to read on the
page or download as a PDF: how full the hall was, peak bandwidth, switch outages, the ports with the
most problems and every incident.

| In the report | Where it comes from |
| --- | --- |
| Most seats online, per hour | The port reads ([stats](stats.md)): seat ports that were up |
| Most seats checked in, per hour | The check-in history |
| Peak bandwidth, bandwidth per hour, data moved | The port reads; data moved is estimated from the hourly averages |
| Switch outages | The status monitor: each time a switch went offline and came back |
| Top problem ports | The needs-attention watch: how often each port started flapping, rising errors, half duplex or online without a check-in |
| Incidents | The incident board: opened, where, what, team, how long until fixed |

The port reads are folded into one row per hour and kept for **21 days**, in Redis with the other
stats (`floorbit:stats`). Switch outages (up to 5,000 changes) and problem ports (up to 1,000 ports)
are kept since the last new event.

## Compared with the last event

With an archived event ([past events](events.md)), the page compares this event so far with
the last one's first as many hours: bandwidth, data moved, seats online, incidents and outages,
with the change in percent. See [stats](stats.md#compare). The PDF doesn't have it yet.

## Download as PDF

**Download PDF** gives the same report as a PDF on A4 (`GET /api/report.pdf?lang=en|de&tz=<minutes>`),
in the page's language and the reader's time zone. Floorbit draws it itself with the PDF's built-in
fonts (`floorbit/pdf.py`), so there is nothing to install.

## Personal data

The report has seat numbers, switches, ports and times, no nicks or IPs. An admin
(`settings.manage`) can turn on **Include nicks and IPs**: the page and the PDF then add the nick and
IP of each problem port's seat and the incidents' seats, and who reported each incident. Every such
download goes to the audit log. The PDF says on its first page that it holds personal data.

## Start a new event

**Start a new event** (admins) clears the report's history: the hourly rows, the switch outages, the
problem ports and the bandwidth peak. Incidents and check-ins stay on their own pages; the report
counts the incidents opened since the new event started. Use it before doors open, after the setup
and load tests.

## API

| Request | Needs | What |
| --- | --- | --- |
| `GET /api/report` | `floorplan.view` | The report as JSON; `?people=1` adds nicks and IPs (`settings.manage`) |
| `GET /api/report.pdf` | `floorplan.view` | The PDF; `lang`, `tz` and `people` as above |
| `POST /api/report/new-event` | `settings.manage` | Start a new event |
