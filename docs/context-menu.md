# The right-click menu

Right-click anything on the floor plan for what you can do with it (#54). On a touch screen, hold a
finger still on it for about half a second. With the keyboard, select something and press the Menu
key or **Shift+F10**.

| Under the pointer | Entries |
| --- | --- |
| A seat | **Seat details and port** (the seat's switch port, link and traffic in the inspector), **Edit seat mapping** (opens Seat mapping filtered to the seat), **Report an incident**, **Bounce the port** |
| A switch | **Show ports** (the inspector with its ports), **Show in inventory**, **Rename**, **Delete** |
| A seat block | **Edit**, **Delete** |
| Several selected items | **Delete** them all |
| Empty floor | **Add a switch here**, **Add a seat block here**, **Fit to screen**, **Reset zoom** |

An entry only shows when your account may use it, and when its feature is on:

| Entry | Needs |
| --- | --- |
| Rename, Edit, Delete, Add here | `floorplan.edit` |
| Edit seat mapping | `seats.edit` |
| Report an incident | the incident board ([incidents.md](incidents.md)) |
| Bounce the port | `ports.act` and a port actions plugin ([ports.md](ports.md)) |

The server checks every request anyway; hiding an entry only saves a click that would be refused.

In the menu, the arrow keys move between entries, Enter picks one, and Escape or a click elsewhere
closes it. Right-clicking a switch or block also selects it, so the inspector shows what the menu is
about.

## Entries from plugins

A plugin can add entries for seats and switches that run one of its actions, such as looking up a
seat's ticket or opening the switch in another tool. They show below the built-in entries, to
accounts that may run the action, and a `danger: true` action asks first. The result shows as a
message at the bottom of the screen, and every run is in the audit log like any plugin action.

```yaml
uses: [actions, context_menu]
actions:
  - {id: lookup, label: Look up ticket, permission: seats.view, params: [{key: seat, type: string}]}
context_menu:
  - {action: lookup, targets: [seat]}
```

The action gets the seat number as `seat` or the switch name as `switch`. See [plugins.md](plugins.md).

The code is `static/js/editor/menus.js`; the long press is in `static/js/editor/touch.js`.
