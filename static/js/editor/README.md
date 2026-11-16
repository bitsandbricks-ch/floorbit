# Floor plan editor scripts

The editor (`templates/index.html`) is plain JavaScript with no build step. It used to be one
3,000-line `app.js`; it is now split by feature so that two changes to different parts of the
editor touch different files.

The files are **classic scripts that share one global scope**: a top-level `let`, `const` or
`function` in one file is visible in every file loaded after it. `index.html` loads them in this
order, and `main.js` runs `init()` last, once everything is defined:

| File | What lives there |
| --- | --- |
| `core.js` | State, DOM references, localStorage, the `api()` helper, toasts, dialogs, undo/redo, utils. |
| `halls.js` | Halls: which one is shown (`?hall=`), the hall picker, the background image, and the Halls dialog (add, rename, delete, background, CSV import of seat blocks). Loaded before `data.js`, whose lists keep only the shown hall's items. |
| `data.js` | Creating, changing and deleting switches and seat blocks; group actions; loading data. |
| `sidebar.js` | Seat numbering, search, tool selection, NetBox sync. |
| `canvas.js` | Coordinates, placing items, pan and zoom, box select. |
| `modals.js` | The add-switch and seat-block dialogs. |
| `render.js` | Drawing switches, seat blocks and seats. |
| `inspector.js` | Selection and the inspector panels. |
| `drag.js` | Dragging one item or a group. |
| `menus.js` | The right-click menu (entries per seat, switch, block, group or empty floor, each only when the account may use it) and the rename dialog. |
| `keyboard.js` | Keyboard shortcuts. |
| `status.js` | Switch list filter, LibreNMS status refresh, top bar stats. |
| `layers.js` | Layer toggles and the grid. |
| `heatmap.js` | The traffic heatmap layer. |
| `incidents.js` | Open incidents as rings on seats and switches, and the count in the top bar. |
| `tournament.js` | Match seats (tournament zones) with a gold outline. |
| `seat-states.js` | The seat states layer: seats online, offline or unknown, and checked in, drawn like the Seats view (`/plan`). |
| `security.js` | Active security findings as dashed rings on seats and switches, and the count in the top bar. |
| `logs.js` | Seats and switches with syslog warnings in the last 10 minutes, underlined in cyan. |
| `power.js` | The power layer: seats and switches coloured by their circuit's load, distribution boards, and the count of red circuits in the top bar. |
| `mutes.js` | Muted switches: a bell-off badge on the pin and "alerts muted until" in its tooltip (the mutes come from `problems.js`), and muting, extending or unmuting a switch from its right-click menu. |
| `problems.js` | The count of current problems next to Problems in the top bar. |
| `ports.js` | Port actions on the selected seat (bounce its port) and flagging a seat for a tech. |
| `touch.js` | Phones and tablets: one finger pans, drags and taps like the mouse, two fingers pinch to zoom; the sidebar as a drawer. |
| `focus.js` | Opening the floor plan on one switch or seat from a link (`/?switch=<id>`, `/?seat=<seat>`), as the Problems list does. |
| `notice.js` | The crew notice from a lead, as a banner under the top bar. |
| `marks.js` | Text labels, walls, zones and icons on the plan: the Draw menu, placing, moving and the inspector (`floorbit/plan_marks.py`). |
| `align.js` | Alignment guides while dragging seat blocks: edges, middles, seat rows and equal spacing; Alt places freely. |
| `groups.js` | Groups of seat blocks (`group`): select, move, turn and copy as one, Ctrl+G and Ctrl+Shift+G; merging blocks next to each other (`floorbit/block_merge.py`). |
| `gaps.js` | Gaps inside a seat block: room in every row after a column, lanes between rows (`col_gaps`, `row_gaps`, as `floorbit/seat_gaps.py`); the Gaps section of the block inspector and the seat's right-click entries. |
| `panels.js` | The tool rail on the left and the panel on the right (search, layers, switches; keys `/`, `L`, `W`), which steps aside while an inspector is open; German for the rail and the panel. |
| `main.js` | `init()` and start-up. Always last. |

Rules that keep this working:

- Code that runs while a file loads (not inside a function) may only use names from the same
  file or an earlier one. Functions are fine to call across files once `init()` runs.
- A new feature gets its own file, added to the list in `index.html` before `main.js`.
- `live.js` (live updates) loads after the editor and uses its globals.
