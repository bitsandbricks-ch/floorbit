### Fixed

- A data file that is valid JSON but not an object (a hand edit gone wrong, such as `[]`) no longer
  stops Floorbit from starting: it starts from empty, says so in the log, and the next save mends
  the file. Audit log lines that aren't entries are skipped like broken ones.
