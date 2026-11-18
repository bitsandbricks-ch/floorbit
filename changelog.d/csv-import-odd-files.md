### Fixed

- Importing a seat map or seat blocks from a CSV file with a very long field (over 128 KB) gave a
  server error; it now says which line cannot be read. A file with the same column twice is refused
  instead of quietly using the last one.
