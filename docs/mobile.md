# Phones and tablets

The floor plan works on a phone (issue #11): look up a seat or switch, see its status, and make
simple changes by touch. The kiosk and check-in pages are unchanged; they have their own layouts.

## Floor plan

| Gesture | What it does |
| --- | --- |
| Tap a switch, block or seat | Selects it and opens its details |
| Drag a switch or block | Moves it (undo works as with the mouse) |
| Drag the empty plan | Pans |
| Pinch with two fingers | Zooms, and pans while you pinch |
| Hold a finger still on a seat, switch or the plan | Opens its [menu](context-menu.md), like a right-click |
| ☰ in the top bar | Opens search and the layer list as a drawer |

Below 760 px wide:

- Search and the switch list live in a drawer behind ☰. Picking a result, tapping the plan or
  pressing Escape closes it.
- The details of what you picked open as a sheet from the bottom, at most about half the screen, so
  the plan stays visible.
- The top bar keeps its icons and scrolls sideways if they don't fit; the brand name, status chips
  and last-updated time are hidden.
- The **Switch** and **Seat block** tools are hidden: placing new things wants a mouse. Selecting, moving,
  renaming and the inspector work by touch.

`static/js/editor/touch.js` turns one finger into the mouse events the editor already handles, so
the other editor files know nothing about touch. Two fingers become a pinch. The toolbar and zoom
buttons are ordinary buttons and get ordinary taps.

## Other pages

The React pages (Problems, Health, Security, Incidents, Electrics, ...) are built on Mantine and fit
a phone as they are. The settings pages wrap their header links instead of widening the page.

`scripts/screenshots.py` takes every page at phone width too, so a layout that breaks on a phone
shows up in the pull request screenshots.
