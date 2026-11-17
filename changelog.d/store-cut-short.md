### Fixed

- A `data.json` (or other state file) left half-written by a full disk or a killed pod no longer stops Floorbit from starting. Every save first writes a complete copy beside the file (`data.json.next`); Floorbit falls back on it, says so in the log, and the next save mends the file. When even the copy can't be written, the file itself is left untouched.
