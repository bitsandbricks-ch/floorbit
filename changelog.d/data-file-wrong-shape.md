### Fixed

- A `data.json` edited by hand into a list or a number no longer starts Floorbit empty, without any
  accounts: it reads the last complete copy, like after a write cut short, and keeps the edited
  file as `data.json.wrong-shape`.
