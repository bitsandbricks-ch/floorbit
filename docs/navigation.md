# Navigation

Every crew page (the floor plan, the React pages, Settings, users and the audit log) has the
same navigation: a sidebar on a computer, a bar at the bottom on a phone.

## Sidebar

- The **event** you work on is at the top: click it to switch to another event of this tenant.
- **Favourites** come first: the star on a row (it shows when you point at the row) pins that page
  there, and a second click takes it off again. A dashboard's **Pin to sidebar** puts it there too.
  They are kept with your account, so they follow you to every browser (`GET` and
  `PUT /api/auth/me/nav`); without sign-in this browser keeps them.
- **Overview** and **Floor plan** are always at the top.
- The other rows are in groups: **Work** (Helpdesk), **Monitoring** (Services, Network, Agents),
  **Seats and inventory** (Seats, Inventory), **Tools** (Switch console, Pre-flight, Logs) and
  **Screens** (Dashboards). A click on a group's name folds it, and this browser remembers it. The
  group of the page on screen is always open.
- Most rows hold several pages, shown as tabs under the top bar: **Helpdesk** has Problems,
  Incidents, My jobs, Handover and Status updates; **Network** has Topology and Firewalls;
  **Seats** has Seat mapping, Check-in, the seat walk-through and IP and MAC history;
  **Inventory** has Cables and Electrics; **Switch console** has the switch commands and the
  terminal; **Agents** has Telemetry; **Dashboards** has Widgets.
  Each tab keeps its own address.
- **Events** sits under Overview and Floor plan: the event list, with the event's own pages
  (schedule, changelog, replay, report, floor plan templates) as its tabs. The picker at the top
  only switches the event this browser works on (issue #1201).
- **Plugins** and **Settings** are named rows at the foot, above your name.
- The button at the bottom folds the sidebar to icons, and back. The choice is kept in a cookie
  (`floorbit_nav`), so every page starts with the same width.
- Your name at the bottom opens the account menu: language, light or dark theme, notifications,
  the crew notice (leads) and **Sign out**.

Above each page a bar shows where you are (group, page, sub page), **Go to** (**Ctrl K**, **⌘K** on
a Mac) for any page, seat or switch, and the bell with what needs a look.

## Settings and Plugins

**Settings** is one page with tabs: **General** (the event, its look, seat sources, monitoring),
**People** (users, roles and teams, sign-in, API tokens), **Alerts** (Discord, crew alerts,
webhooks), **Tenants** and **System** (status, backup, caching, features, sidebar sections, the
audit log). Each part keeps its own address (`/settings/users`, `/settings/audit`, ...), and the
search on top finds any field. An account sees only the tabs it may open: someone who manages
accounts but not settings gets People alone.

**Plugins** (`/settings/plugins`) has **Installed**, **Marketplace** and **Updates** (installed
plugins with a newer version). NetBox, LibreNMS and every other plugin keep their settings on their
own plugin page.

## Your own sections

Admins add sections of their own under **Settings > Sidebar sections** (`/settings/sidebar`): a
name, an icon and links. A link opens a dashboard, one of Floorbit's pages, or an address of its
own (a path on this server such as `/plan?seat=A-1`, or `https://...`, which opens in a new tab).
Every link can have its own name; without one it shows the dashboard's or the page's name.

They sit under the pinned pages, above Floorbit's sections, in the order the admin put them, and
fold like the others. Everyone sees only the links they may open: a page their role can't open or a
dashboard that was removed is left out, and a section with nothing left is hidden. A saved change
shows in every open sidebar without a reload.

The sections are kept in `data.json` under `nav_sections` (`floorbit/nav_sections.py`).
`GET` and `PUT /api/settings/sidebar` read and replace all of them (admins only); everyone else
gets their own view with the page list (`custom` in `GET /api/pages`).

The sidebar lists only the pages this account may open and the features that are on, the same
list as **Go to** (`GET /api/pages`). A page Floorbit doesn't sort into a section yet shows under
**More**.

Between the React pages only the page changes: the sidebar stays, nothing reloads.

## Phones

Below 768 px the sidebar becomes a bar at the bottom with **Overview**, **Floor plan**,
**Incidents**, **Problems** and **Menu**. **Menu** opens everything else as a sheet from the left, with the
search and the account menu. The brand and a search button sit at the top of each page.

## For developers

The sidebar is `frontend/src/nav/`: one React component for both kinds of pages. The React app
draws it in `components/Layout.tsx`; the server pages include `templates/_nav.html`, which loads it
as the second entry of the Vite build (`src/nav/entry.tsx`). The server puts the page list, the
brand and the account into the page (`floorbit/nav.py`), so the sidebar draws without waiting for
an API call. Without a frontend build the server pages show a plain list of links instead.

On the server pages the sidebar is in the first paint, before the floor plan: the build writes
`static/app/nav-shell.json` (icons, order and texts, from `frontend/buildtools/nav-shell.ts`), and
`floorbit/nav.py` draws the same markup as `Sidebar.tsx` from it into `#fb-nav`. The script then
takes it over in one commit. The server picks the language from the `floorbit_lang` cookie (the
frontend writes it) or `Accept-Language`. A change to the sidebar's markup in `Sidebar.tsx` needs
the same change in `nav.markup()`.

A new page goes into `floorbit/page_index.py` as before, and into a group in
`frontend/src/nav/sections.ts` (with an icon). A page that is a tab of another one (the admin pages
in Settings) goes into `INSIDE` there instead, and into `PAGES` and `TABS` in `pages/Settings.tsx`. Pages Flask draws itself are listed in
`isServerPage()` there, so links to them load the whole page.
