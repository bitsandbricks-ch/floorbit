# Phones and tablets

Floorbit works on a phone: look up a seat or switch, see what is wrong, and change the floor plan by
touch. The kiosk and check-in pages are unchanged; they have their own layouts.

## Install it as an app

Floorbit installs on a phone's home screen like an app, with its own icon and without the
browser's address bar. There is no app store and nothing to set up on the server.

- **Android (Chrome):** open Floorbit, then ⋮ › **Install app** (or **Add to Home screen**).
- **iPhone and iPad (Safari):** open Floorbit, then Share › **Add to Home Screen**.

The installed app is the same Floorbit as in the browser, and updates with it. It keeps the app's
own files on the phone so it opens quickly, but never the data: seats, switches and problems always
come live from the server. Without a connection it says so and offers to try again.

## Floor plan

Below 768 px wide the plan takes the screen. On top: a search box with the online count, and a
small Map, List and Topology switch. At the bottom, a dock with **Layers**, **Problems**,
**Views**, **Edit** (for those who may edit) and **More** (another hall, the big screen, export).
The details of what you tap open as a sheet from the bottom.

| Gesture | What it does |
| --- | --- |
| Tap a seat, block or switch | Opens its details |
| Drag the plan | Pans |
| Pinch with two fingers | Zooms, and pans while you pinch |
| Hold a finger still on a seat, switch or the plan | Opens its [menu](context-menu.md), like a right-click |

## Editing the floor plan

**Edit** in the dock starts editing; **Done** in the bar on top ends it. The tool picker sits in the
plan's corner. The edit panel stays a slim bar under the plan with what you picked, **Details**,
undo and redo, so it never covers what you are moving; **Details** or its grab bar brings it up.

With the Select tool:

| Gesture | What it does |
| --- | --- |
| Tap an item | Picks it |
| Drag an item | Moves it (undo works as with the mouse) |
| Hold a finger still on an item | Opens its menu: copy, rotate, lock, delete … |
| Drag empty space | Pans the plan |
| Tap empty space | Clears the pick |
| Hold a finger still on empty space, then drag | Draws a box and picks what is inside |
| Pinch with two fingers | Zooms and pans, also in the middle of a drag (the drag is dropped) |

The drawing tools (walls, zones, cables …) draw with one finger; two fingers still pinch. Key hints
show only where there is a keyboard.

## Other pages

Every page fits a phone. The pages are in the bar at the bottom, and **More** holds the rest, the
status line and the footer links (see [Navigation](navigation.md)). Tabs that don't fit go under
**More** in their row, filters open as a sheet, and wide tables show each row as a card.

`scripts/screenshots.py` takes every page at phone width too, so a layout that breaks on a phone
shows up in the pull request screenshots.
