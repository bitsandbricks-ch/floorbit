# Dashboards

A dashboard is a set of widgets on a grid, saved under a name. Put one on the TV at the ops desk, a
wall in the hall, or your own second monitor. Widgets can be grouped in named sections, and a widget
can be split into panes side by side or stacked. Each pane shows one thing:

| Pane | What it shows |
| --- | --- |
| **Plan** | A hall's floor plan: the whole hall, one seat block, one row, a zone you drew on the plan, or a view you zoomed to. With a layer preset (Overview, Network, Electrical, Ops), a seat filter, how seats are numbered and which plan marks it draws. |
| **Saved widget** | A widget saved on the Widgets page, see [Saved widgets](#saved-widgets). The pane follows it: change the widget and every dashboard that shows it changes too. **Clone into this dashboard** in the pane's settings turns it into a tile of its own with the same settings, for this dashboard only. |
| **Tile** | One data widget that fits its box: Floorbit's own (problems, incidents, open incidents, switches, switch states, seats, seats by block, switches down, traffic, bandwidth, peak, ports, uplinks, busiest seats, internet uplinks, LAN cache, agents, and with their feature on: service health, power load, DNS lookups, top and blocked sites, game launchers, Wi-Fi clients and access points, and traffic by kind, top services, traffic by area, and what looks odd) or a plugin's. See [Tiles that fit their box](#tiles-that-fit-their-box). |
| **Text** | Your own words: a welcome, the schedule, the Wi-Fi name. A small Markdown (`# heading`, `- list`, `**bold**`, `[link](https://example.com)`); every line stays its own line. Four sizes (S to XL) that grow with the pane, aligned left or centred. |

For example: the whole hall on the left, the VIP zone zoomed in at the top right, and the network
layer at the bottom right.

## Making one

**Dashboards** in the sidebar lists them; **New dashboard** opens the editor (needs
`floorplan.edit`, like the tile layouts). The editor takes the whole screen: the sidebar, top bar
and tabs step aside until you leave it with **✕** (or **Cancel**). One bar on top holds the name
(click it to rename), **Add widget**, **Add section**, the layout, **Dashboard settings** (rotate
halls, time shown, header in full screen, sound, public), **Save** and, under **⋯**, **Make a copy**,
**Reset to default** and **Delete**, which ask first. Picking a widget opens its settings over the
dashboard; pick another widget and they switch, **✕** closes them, and the dock button keeps them
beside the dashboard instead (remembered in this browser). On a phone the buttons sit in a bar at
the bottom and the settings open as a sheet from below.

- **Add widget** puts an empty widget in the first free spot of the picked section. Drag a widget by
  its handle (top left) and resize it by its corner (bottom right); the others make room and
  everything floats up, on a grid of 24 columns. With the keyboard: focus the handle, then the arrow
  keys move it and Shift with the arrow keys resizes it. Up to 24 widgets. While you resize, the
  size in cells shows on the widget, and each widget shows the level it draws at (Small, Medium,
  Large) at the bottom right, so you see what the box gives before you save. A list that doesn't
  fit says how many of its rows show ("Medium · 5 of 7 rows"), in amber, and a widget whose box is
  too small even for Small says "Too small" instead. The settings panel of the picked widget says
  the same in words: "Draws as Medium at this size", and what to do when rows are cut or the box is
  too small.
- **Add section** starts a named section below the others. A section's title is optional: without
  one it is just a divider line. Sections fold (the arrow before the title), move up and down, and
  can be removed with their widgets. Folding on a screen is only for whoever looks at it; folding
  in the editor is saved.
- **Layout**: **Screen** fits the whole dashboard into the space it has, nothing scrolls: under
  the top bar in the app, the whole screen on a wall. Widgets drop a level when their rows get
  short. **Page** gives rows a fixed height and scrolls like any other page; a widget's height
  snaps to small (3 rows), medium (5) or large (8), and above that goes a row at a time. New dashboards start as
  a Page. On a phone, both scroll, one widget per row in reading order; small numbers (a quarter of the width, up to M high) sit two side by side. A Page opened full screen (or in a
  rotation) offers whoever may edit it **Make it a Screen**; **Keep it a Page** stops asking on
  that screen.
- Click a pane to set it up in the panel on the right.
- **Split right** and **Split down** cut a pane in two; drag the border between two panes to resize
  them. Up to 40 panes on a dashboard, splits up to four deep.
- **Plan** panes show their hall's name and area as a title, and how many of the seats in that area
  are online or have problems. A title you type replaces it.
- **Hide the title** leaves a pane's head off, for a cleaner wall (on a plan pane, the online count
  goes with it).
- **Row** shows one row of a block: a block can hold several rows, and the crew works a row at a
  time. The rows are named as everywhere else (C, or A 2 in a block numbered as a whole), and the
  online count is that row's seats.
- **Zone** lists the zones of the hall that have a label: draw one around the VIP area with the
  editor's Zone tool first. **My view** shows a small plan: move and zoom it, then **Use this view**.
- **Plan marks** on a plan pane: **All** draws the marks of its layers, **Public** only the Overview
  and Safety marks (as the attendee pages do), for a screen people walk
  past, and **None** none.
- **Shows** on a plan pane:
  - **Its area**: the whole hall, a block, a row, a zone or a box, as picked below.
  - **One saved view**: a view saved on the floor plan (see [Saved views](halls.md#saved-views)), with
    where it looks and its seat filter. The pane's layer preset still decides the layers.
  - **Tour**: goes through its stops, 8 to 60 seconds each: the pane's whole area, each block in turn
    (top to bottom, left to right), and saved views of the hall. The stop's name shows in the corner,
    a bar along the bottom shows how many are left, and the mini-map shows where a zoomed stop is.
    With **When a seat gets a problem: Show it next**, a seat that just got a problem makes the rows
    around it the next stop. Touching the screen pauses the tour for a minute.
  - **Overview + spotlight**: the whole area on the left, colour only, with the stop outlined, and the
    stop zoomed in on the right. The spotlight stays on the newest problem while it lasts, and goes
    through the stops when nothing is wrong. A box narrower than 560 pixels shows the area instead.

  Tours and views list the hall's shared views only: a private one would show to nobody else. A public
  dashboard gets those shared views with its panes.
- **Public** lets the dashboard open without signing in (below).
- **Rotate halls every** makes plan panes without a fixed hall that show a whole hall go through all
  halls in turn.

## Tiles that fit their box

A tile pane never scrolls inside. It draws its data at one of three levels, picked from the size of
its box:

- **Small**: a number and its state (28 of 30 switches up, with how many are down or warning).
- **Medium**: the rows that fit, worst first, ending in **+N more**; or a graph with its legend.
- **Large**: the details. Tables page, sort (click a column) and filter inside the box; graphs add
  the time axis and each line's maximum and average. On a full screen a list that has more pages
  turns to the next one every 12 seconds by itself, since nobody clicks a wall (and it has no
  filter box there); pointing at it stops that.

Hover a graph (or touch it) for the time and every line's value under the pointer; a cut-off row or
number shows in full on hover. **+N more** and the **Make large** button show the tile at its large
level in the whole dashboard area; the sidebar and the time stay. The address gets `?w=`, so the
browser's Back and a shared link work. **Back to the dashboard** or Esc goes back, and on a full
screen it goes back by itself after a minute. **Details** jumps to the page behind it.

In a large **Switch states** or **Switches down**, a switch's name opens its glance beside the list:
what it is (role, model, management address), where it is, how many ports it has, what is wired to
it, what goes down with it, and links to its device page, its ports and its telemetry. Esc closes
the glance first, then the large view. A public screen nobody signed in to has no glance.

In the pane's settings, **Show as** draws the same data as another kind where it makes sense:

- a status as a number of what is up, as bars or as a pie of how many are in each state;
- a number with a scale (switches up out of all, seats online) as a **gauge**;
- a list with numbers as **horizontal bars** or **vertical bars** (an item with its own maximum,
  such as seats online out of a block, fills its own track) or a **pie** (seven slices at most, the
  rest as "Other");
- a graph as **vertical bars**: each bar is the average of its slice of time, one bar per line;
- numbers or samples as a **histogram**: how many values fall in each range (ranges of a round
  width, such as 0–5, 5–10);
- a table with number columns as bars, one segment per column;
- a list as a table, a table as a list.

Where the data has two or more lines (download and upload) or number columns, **Bars and lines**
puts them **side by side**, **stacked**, or **stacked to 100 %** to show each one's share. A graph
draws as a **line** or an **area**. **Trend line** adds a dashed line over each line of a graph or
time bars: a **straight trend** over the time shown, or a **rolling average** that smooths the
spikes. The options only show where they mean something for the data.

### More sources, groups and calculations

A tile pane can **draw together with** up to three more tiles. The first tile decides the shape:
lines over time gain the others' lines (only with the same unit, such as bit/s), numbers become one
bar per tile, status lists add up, and lists and tables join on their first column. A tile that
doesn't fit is left out, and the pane says which.

**Group by** turns rows into one bar per group: switches by state, ports by hall. **Calculate** picks
count, sum, average, min, max, first or last: with a group, it is the number of each group (from
the last number column); without one, the data becomes one number (one per line for a graph), such
as the average traffic over the time shown. **Legend shows** picks the numbers a graph's legend
gives for each line; empty, it shows the latest value, plus max and average when large.

### Numbers and colours

Under **Numbers and colours** in a tile pane's settings:

- **Unit** replaces the data's unit, **Decimals** fixes the decimals, and **Short numbers** writes
  1,234 as 1.2k.
- **Colour steps** colour the number, bar or gauge from a value up (≥ 80 orange, ≥ 95 red), or
  from a share of the maximum (**% of max**, for seats online out of a block). Graphs draw each step
  as a dashed line.
- **Show values as text** turns a value or a range into a word in a colour, such as 0 as "Down" in
  red.
- **Sort**, **Show at most** and **Hide rows that are 0** pick which rows a list or table shows:
  biggest first and at most five is a top 5.
- **Time shown** for the whole dashboard (in its settings): every graph that can follows it, unless
  its pane picks its own time. Anyone looking at the dashboard can pick another time for themselves
  with the time menu next to Edit; it goes into the address (`?range=6h`), so a big screen can be
  opened with it too.
- **Time shown** (tiles that offer it, such as Traffic): the last hour, 6 hours, 24 hours, or the
  whole event by the hour. **Compare with yesterday** adds a dotted line with yesterday's traffic at
  the same times, by the hour. **Mark what happened** draws a line where a switch went down or came
  back, and where an incident started (incidents only for crew who may see the board); hover names
  them. Up to 50 of the latest show.
- **History under the number** and **Show the change** (a number drawn from data over time): a
  small line of how it went, when the pane is too small for the graph, and an arrow with how much it
  moved since an hour ago (or since the start of the data, when that is shorter).
- **Number size** makes the big number of a number, gauge or pie smaller or larger, for a wall seen
  from afar or a crowded screen.
- **Refresh** sets how often the pane asks again (every 10 or 30 seconds, every minute or every 5
  minutes) instead of the tile's own pace.
- **Value axis** (graphs) fixes where the axis starts and ends, so graphs side by side on a wall
  compare, and **Log scale** draws values far apart (bytes, lookups) readably. Values outside the
  ends sit on the edge.
- **Series** (graphs) or **Rows** (lists) set one by its name in the data: **Show as** another
  name, a colour of its own, or **Hide**. A setting whose series is gone stays until you remove it.

Hover a bar, a slice or the gauge for its value and share. **Size** pins small, medium or large
instead of picking it from the box. Any box size works.

## Finding a dashboard

The Dashboards list is one table (#897): a small preview of the grid, the name with its badges and
tags, the group, where it shows (**Public**, on how many screen accounts, or only **Inside the app**),
when it last changed and who changed it, a pin for the sidebar and **⋯** (open, big screen, edit, export as file).

- **Search** looks in the names, tags and groups.
- **Show** keeps the pinned ones, your own, the ready-made ones, the public ones or the ones from
  plugins.
- **Tag** and **Group** narrow the list once a dashboard has one. A click on a tag in a row filters by it.
- Search and filters stay in the address, so a link shows the same list.

Tags (up to 8 short words, such as `noc` or `hall-a`) and a group (such as *Network crew*) are set
under **Dashboard settings** in the editor. A public screen doesn't get them.

## Saved widgets

**Widgets** (`/widgets`, also a button on the Dashboards list) has two tabs (#1009):

- **Widgets** are the saved ones: a tile with its sources and settings (type, size, grouping,
  numbers and colours) kept under a name, drawn live as a dashboard shows it. **New widget** makes one
  from a type; **Copy** makes a new one from an existing widget; **Edit** changes it, and every
  dashboard that shows it changes with it. **Add to** puts it on a dashboard as a saved-widget pane.
- **Types** are every kind of widget Floorbit can draw (the gallery below). **Save as widget** starts
  a new widget from a tile type.

Everyone who may edit dashboards (`floorplan.edit`) may make, change and remove widgets. A widget that
a dashboard still shows can't be removed: clone it there or take it off first. A public dashboard
gets the widget's tile itself, under the same rules as a tile pane. API: `GET/POST /api/widgets`,
`PUT/DELETE /api/widgets/<id>`.

## The widget gallery

The **Types** tab shows every widget there is, live, with your data: Floorbit's own and the tiles of the plugins that are on. Filter them by area (Network,
Services, Traffic, Power, Plugins) or search by name. **Add to** puts it at the end of a dashboard
you pick. A widget whose feature is off says so instead of its content.

Every widget is a tile that fits its box. What needs more room than a box, like the health checks'
numbers and mutes, IP and MAC search, forecasts and comparisons, resetting the peak or posting a
network status update, is on its page (Health, IP and MAC, Stats, Status updates, ...). The rich
widgets that drew a whole page inside a pane are gone: a dashboard saved with one shows the tile
that matches it (service health, the LAN cache, seats by block, Wi-Fi clients, agents, traffic, DNS
lookups, game launchers, downloaded, power circuits), or an empty pane where there is none
(endpoints, network status, speed tests).

## Ready-made dashboards

Floorbit comes with these. Change any of them; saving keeps your version under the same name, and
the list marks it **Changed**. **Reset to default** under **⋯** in its editor drops your version and brings the
ready-made one back (it asks first, since the changes are lost). **Make a copy** under **⋯** in any dashboard's
editor saves it as a new dashboard of your own, named "… (copy)" and not public, and opens it.

| Dashboard | What is on it |
| --- | --- |
| **Kiosk** | The big screen in the hall (below). Public. |
| **Overview** | Seats, bandwidth, switches, incidents, agents and the LAN cache as numbers; the plan, service health and switches down; switch states, uplinks, the busiest seats, traffic by kind and what looks odd. Bandwidth over time is on Traffic; the bandwidth tile leads there. Below, **During the event**: seats online and checked in, seats that moved, incidents and switch outages so far, traffic since the event started and the ports with the most problems, from the event report. The printable report stays under its export. |
| **Service health** | Services up, switches, LAN cache and agents as numbers; every check worst first, internet uplinks and switches down. Each check's numbers and mutes are in its panel on the Services page. |
| **Network** | Switches, seats, bandwidth and ports in use (only ports that went down count as down); switches down, uplinks, the busiest seats and switch states; Wi-Fi clients, access points and seats online by block. IP/MAC search and network status updates are on their pages. |
| **Services** | Services up, the LAN cache, DNS lookups and agents; service health and internet uplinks; top and blocked sites and game launchers. Adding and editing services is on the Services page. |
| **Traffic** | Bandwidth, the peak and what looks odd; traffic over time and by kind; top services, traffic by area and the busiest seats; DNS lookups, the LAN cache, top and blocked sites and game launchers. Speed tests are on their page. |
| **Power load** | Every circuit's load, fullest first. The boards in detail are on the Power page. |
| **Event in numbers** | The stats wall for the hall and attendees' phones: seats online, downloaded, the busiest moment and hour, most seats online, the most loyal block, the LAN cache and the top games, a tile each. Public, Screen layout. |

A plugin can ship ready-made dashboards of its own widgets too (`dashboards:` in its
`plugin.yaml`, see the [plugin spec](plugin-spec.md#screens)). They are listed while the plugin is on,
marked **From <plugin>**, and work like the ones above: change one and **Reset to default** brings the
plugin's back.

## Moving a dashboard to another Floorbit

**Export as file** under **⋯** in a dashboard's editor downloads it as saved, as a
`<id>.dashboard.json` file. **Import** on the Dashboards page reads such a file in as a new
dashboard, under a free name (`desk`, then `desk-2`). Anyone who may open a dashboard can export
it; importing needs `floorplan.edit`.

The file holds the layout only: sections, panels, panes, and the dashboard's settings. It never
holds secrets, seat data or anything about a person, and who saved it and when stay behind. A saved
widget goes in as a tile pane of its own, since the other Floorbit doesn't have it. An imported
dashboard is never public until someone switches that on. Tiles from a plugin the other Floorbit
doesn't have stay in the file; after the import a note names those plugins, and each such pane says
which plugin it needs until it is installed and on.

## Kiosk

**Kiosk** is a ready-made dashboard for the big screen in the hall, and what `/kiosk` opens: the
first hall's plan with the public marks only, and beside it how many switches are up, how many
seats are online, and which switches are down and for how long. It is public. Change it like any
other; saving keeps your version under the same name, and **Reset to default** brings the
ready-made one back. See [kiosk.md](kiosk.md).

## Public dashboards

A dashboard with **Public** on opens without signing in, for a screen in the hall or a link on the
event website. Signed out, it shows only what anyone may see:

- **Plan** panes: seats online or offline, taken or checked in and their traffic, switches by name
  and status, and the public marks only (a pane set to **All** draws the public ones). No nicks,
  IPs, MACs, notes, seat problems, power boards or patch panels, and no power, firewall, Wi-Fi or
  crew layer.
- **Tiles**: Floorbit's switches, seats online and switches down tiles, and the event in numbers tiles
  (the [stats wall](stats-wall.md)), which say so while the stats wall is off.
- **Widgets**: the event in numbers widget, while the stats wall is on.
- **Text** and empty panes.

Any other pane (other tiles and widgets) says it needs an account. Someone signed
in sees the whole dashboard as usual. For a screen that should show more, sign it in with a `kiosk`
account or a custom role ([auth.md](auth.md)).

A signed-out screen reads `GET /api/dashboards/<id>/public` and, below it, `/plan?hall=` and
`/tiles/<tile>`; they answer only for a public dashboard and only for what it shows.

## A screen account for some dashboards

A wall screen's account can be limited to some dashboards: under Settings > Users, **Limit
dashboards** on its row, pick them and save. That account then lists and opens only those (another
one's address takes it to the first of them, `GET /api/dashboards/<id>` answers 404), and `/` starts
on the first. Public dashboards still open, as they do for anyone. An empty list lifts the limit.
It narrows what the account's role allows; the rest of the role stays as it is. For example: a
`kiosk` account for the Hall B wall, limited to the Hall B dashboard.

## On the screen

**Open full screen** opens `/dashboards/<id>`: the same panes without the sidebar, framed by a
slim header (the dashboard's name, the event, the day, the next dashboard of a `?rotate=` list and
the clock) and the status line at the bottom. A public screen nobody signed in to shows the header
without the event and the status line. Switch **Header and status line in full screen** off in the
dashboard's settings for just the panes and a clock in the corner.

While something is down and nobody has taken it (no incident open for it, not muted), a red bar
under the header names it and how long it has been down. A rotating screen goes to the dashboard
whose pane shows it and waits there ([Rotating dashboards](#rotating-dashboards)).
A list pane that shows it as down pulses red with the bar, so the eye finds it. Open an incident or mute it, and the bar goes away. A public screen nobody signed in to shows no
bar: it can't read the problem list.

For the NOC screen, switch on **Sound for new problems** in the dashboard's settings (off by
default). Its full screen then plays a short tone once for each new problem the bar shows. What is
already down when the screen opens stays quiet, so a reload doesn't ring again. Browsers play sound
only after a click on the page: the screen shows **Turn on sound** until someone clicks it. On a
kiosk PC nobody clicks, so start Chromium with `--autoplay-policy=no-user-gesture-required`. A
public screen nobody signed in to plays nothing.

The pointer hides
after three seconds, and the page reloads itself after a Floorbit update. Saved changes reach the
screen within a minute. Someone at the screen can drag and zoom a plan pane; it goes back to its
area after a minute. On a phone the panes are stacked.

Seat numbers follow the zoom ([zoom levels](seats.md#zoom-levels)); set a plan pane's
**Seat numbers** to **Always** or **Never** to override that.

`?hall=<id>` on the screen's address shows that hall on the plan panes without a hall of their own,
for example `/dashboards/kiosk?hall=hall-2`. `?theme=<preset>` picks the look, as on every page
([themes.md](themes.md)); the Kiosk dashboard uses the `kiosk` preset unless the site theme says
otherwise.

### Rotating dashboards

`?rotate=<id>,<id>,...&every=<seconds>` moves on to the next dashboard in the list every so many
seconds (10 to 600, 30 by default), for a wall that shows several: for example
`/dashboards/kiosk?rotate=kiosk,traffic,event&every=45`. The other options (`hall`, `theme`) go
along.

When something goes down and nobody has taken it, the rotation looks for the dashboard with a pane
that lists it: it waits on the one it is on if a pane there pulses, otherwise it moves on after 10
seconds (or sooner, if `every` is shorter). Once it finds one, the header says **Rotation waits**
until the problem is taken. If no dashboard in the list shows it, the screen waits after one round
on the dashboard it got to.

## For developers

Data: `floorbit/dashboards.py` (data.json key `dashboards`), API `GET/PUT/DELETE /api/dashboards/<id>`.
A dashboard is `sections` (each with an optional `title`, `folded` and its `panels`), and a panel is
`x`, `y`, `w`, `h` on the 24-column grid plus a `node` (a pane or a split of panes). Layouts saved
as one split tree (`root`) are read as one panel filling the screen. How panels make room is in
`frontend/src/pages/dashboards/grid.ts`.
A Monitoring page (Health, Wi-Fi, DNS, ...) is one line in `frontend/src/pages/monitoring/pages.ts`
and is drawn by `pages/monitoring/ViewPage.tsx` (one route in `routes/<area>.ts`, one entry in
`floorbit/page_index.py`, a tab in `nav/sections.ts`). `RETIRED_VIEWS` in `floorbit/dashboards.py`
says which tile a saved `view` pane is read as. `GET /api/dashboard` lists the tiles this account may see. Floorbit's own tiles are one line in
`TILES` (`floorbit/dashboard_core.py`) plus their builder in `CORE_TILES`
(`floorbit/blueprints/plugins.py`). What a public dashboard may show is `PUBLIC_TILES` and
`public_board()` in `floorbit/dashboards.py`.

A dashboard asks for its tiles together: `frontend/src/api/widgetBatch.ts` collects the tiles asked
for within 10 ms and sends them as `GET /api/dashboard/widgets?u=<tile url>&u=...` (at most 64; the
browser sends 20 per request). Each tile still runs through its own route and permission check
(`floorbit/blueprints/widget_batch.py`). A source several tiles read (the traffic snapshot, flows,
health, DNS) is marked `@once_per_batch` (`floorbit/batch_share.py`) and read once per batch; a new
builder that reads a shared source should use one of those helpers.
