# Navigation

Every crew page (the floor plan, the React pages, Settings, users and the audit log) has the
same navigation: a sidebar on a computer, a bar at the bottom on a phone.

## Sidebar

- **Go to** at the top opens the search for any page, seat or switch (also **Ctrl K**, **⌘K** on a Mac).
- **Floor plan**, **Seats**, **Dashboard**, **Problems** and **Incidents** are always at the top.
  Problems shows how many switches are down.
- The other pages are folded into sections: **Helpdesk**, **Network**, **Build and teardown**,
  **Event** and **Settings**. The section of the page you are on is open; the others open with a
  click and stay open on this browser.
- The button at the bottom folds the sidebar to icons, and back. On icons, a section opens as a
  list beside the sidebar. The choice is kept in a cookie (`floorbit_nav`), so every page starts
  with the same width.
- Your name at the bottom opens the account menu: language, light or dark theme, notifications,
  the crew notice (leads) and **Sign out**.

The sidebar lists only the pages this account may open and the features that are on, the same
list as **Go to** (`GET /api/pages`). A page Floorbit doesn't sort into a section yet shows under
**More**.

Between the React pages only the page changes: the sidebar stays, nothing reloads. The floor plan,
Settings, users and the audit log are drawn by the server and load as a whole page, with the same
sidebar.

## Phones

Below 768 px the sidebar becomes a bar at the bottom with **Floor plan**, **Seats**, **Problems**,
**Incidents** and **Menu**. **Menu** opens everything else as a sheet from the left, with the
search and the account menu. The brand and a search button sit at the top of each page.

## For developers

The sidebar is `frontend/src/nav/`: one React component for both kinds of pages. The React app
draws it in `components/Layout.tsx`; the server pages include `templates/_nav.html`, which loads it
as the second entry of the Vite build (`src/nav/entry.tsx`). The server puts the page list, the
brand and the account into the page (`floorbit/nav.py`), so the sidebar draws without waiting for
an API call. Without a frontend build the server pages show a plain list of links instead.

A new page goes into `floorbit/page_index.py` as before, and into a section in
`frontend/src/nav/sections.ts` (with an icon). Pages Flask draws itself are listed in
`isServerPage()` there, so links to them load the whole page.
