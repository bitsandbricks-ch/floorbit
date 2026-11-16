### Added

- Patch panels are their own thing on the floor plan: Edit mode has a Patch panel tool (name and port count) and shows which seat is on each port; a cable through a panel picks one of its ports, and each port takes one cable.
- Edit mode has a Cable tool: click a seat, switch or patch panel and the cable form opens with it filled in. Seat cables are drawn on the Network layer in Edit and Network mode, and can be selected, changed, deleted and undone.
- The cable form picks the patch panel and its port from lists, like the switch and its port: only free ports, unless you ask for all.

### Fixed

- Pages with many live parts no longer run out of connections: they share one live update stream, so requests stopped hanging.
