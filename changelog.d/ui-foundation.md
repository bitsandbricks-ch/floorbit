### Changed

- Dropdowns, tabs, inputs and menus share one look on every page: dropdowns pop in with a search box and a check mark, tabs are an underline. The menu, badges and table headers are now as large as the page text.
- Fields that name a switch, a port, a seat, a block or a user are searchable lists of what Floorbit knows instead of free text. A port list shows only free ports and says who holds the others. This covers cables, patch blocks, the walk, the command panel, the log filters, new incidents and the seat form.

### Added

- `GET /api/options/<kind>`: the choices for switches, ports, seats, blocks, halls, firewalls, agents, users and teams.
