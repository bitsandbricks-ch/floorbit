### Fixed

- With SQLite, a save while another program holds the database file (a backup tool, a `sqlite3`
  shell) answers "The database is busy, try again" instead of a server error.
