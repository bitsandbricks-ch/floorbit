# Navigation

Every crew page (the floor plan, the React pages, Settings, users and the audit log) has the
same navigation: a sidebar on a computer, a bar at the bottom on a phone.

## Sidebar

- **Go to** at the top opens the search for any page, seat or switch (also **Ctrl K**, **⌘K** on a Mac).
- **Favourites** come first: the star on a row (it shows when you point at the row) pins that page
  there, and a second click takes it off again. They are kept with your account, so they follow you
  to every browser (`GET` and `PUT /api/auth/me/nav`); without sign-in this browser keeps them.
- **Floor plan**, **Seats**, **Dashboard**, **Problems** and **Incidents** are always at the top.
  Problems shows how many switches are down.
- The other pages are folded into sections: **Helpdesk**, **Network**, **Build**,
  **Event** and **Settings**. The section of the page you are on is open. Opening another section
  folds the open one, so the sidebar stays short. Turn that off in the account menu (**Fold other
  sections when one opens**) to keep several open; they then stay open on this browser.
- The button at the bottom folds the sidebar to icons, and back. On icons, a section opens as a
  list beside the sidebar. The choice is kept in a cookie (`floorbit_nav`), so every page starts
  with the same width.
- Your name at the bottom opens the account menu: language, folding sections, light or dark theme, notifications,
  the crew notice (leads) and **Sign out**.

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

On the server pages the sidebar is in the first paint, before the floor plan: the build writes
`static/app/nav-shell.json` (icons, order and texts, from `frontend/buildtools/nav-shell.ts`), and
`floorbit/nav.py` draws the same markup as `Sidebar.tsx` from it into `#fb-nav`. The script then
takes it over in one commit. The server picks the language from the `floorbit_lang` cookie (the
frontend writes it) or `Accept-Language`. A change to the sidebar's markup in `Sidebar.tsx` needs
the same change in `nav.markup()`.

A new page goes into `floorbit/page_index.py` as before, and into a section in
`frontend/src/nav/sections.ts` (with an icon). Pages Flask draws itself are listed in
`isServerPage()` there, so links to them load the whole page.
