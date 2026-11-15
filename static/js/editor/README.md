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
| `sidebar.js` | Collapsible sections, seat numbering, search, tool selection, NetBox sync. |
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
| `security.js` | Active security findings as dashed rings on seats and switches, and the count in the top bar. |
| `logs.js` | Seats and switches with syslog warnings in the last 10 minutes, underlined in cyan. |
| `power.js` | The power layer: seats and switches coloured by their circuit's load, distribution boards, and the count of red circuits in the top bar. |
| `problems.js` | The count of current problems next to Problems in the top bar. |
| `ports.js` | Port actions on the selected seat (bounce its port) and flagging a seat for a tech. |
| `touch.js` | Phones and tablets: one finger pans, drags and taps like the mouse, two fingers pinch to zoom; the sidebar as a drawer. |
| `focus.js` | Opening the floor plan on one switch or seat from a link (`/?switch=<id>`, `/?seat=<seat>`), as the Problems list does. |
| `main.js` | `init()` and start-up. Always last. |

Rules that keep this working:

- Code that runs while a file loads (not inside a function) may only use names from the same
  file or an earlier one. Functions are fine to call across files once `init()` runs.
- A new feature gets its own file, added to the list in `index.html` before `main.js`.
- `live.js` (live updates) loads after the editor and uses its globals.
