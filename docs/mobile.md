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
| ☰ in the floor plan's top bar | Opens search, layers and the switch list as a drawer |

Below 768 px wide:

- The tools sit in a small bar at the top of the plan. Search, layers and the switch list live in a
  drawer behind ☰. Picking a result, tapping the plan or
  pressing Escape closes it.
- The details of what you picked open as a sheet from the bottom, at most about half the screen, so
  the plan stays visible.
- The top bar keeps the hall picker, the online and offline counts and the refresh button; the
  other status chips and the last-updated time are hidden. The pages are in the bar at the bottom
  (see [Navigation](navigation.md)).
- The **Switch** and **Seat block** tools are hidden: placing new things wants a mouse. Selecting, moving,
  renaming and the inspector work by touch.

The plan works with pointer events, so a finger drags and taps like the mouse, and two fingers
pinch to zoom. The tool rail and zoom buttons are ordinary buttons and get ordinary taps.

## Other pages

The React pages (Problems, Health, Security, Incidents, Electrics, ...) are built on Mantine and fit
a phone as they are. Every crew page has the Floorbit brand and a search button ("Go to") on top
and the bar at the bottom (see [Navigation](navigation.md)). Buttons next to a page's title stay
in one row that scrolls sideways, so the page itself starts on screen.

`scripts/screenshots.py` takes every page at phone width too, so a layout that breaks on a phone
shows up in the pull request screenshots.
