### Security

- The cable list and event changelog CSV exports double a quote inside a cell. Before, a name with a
  quote and a comma in it ended its cell early, and what followed became a cell of its own, which a
  spreadsheet could run as a formula. Cells starting with a tab or carriage return get the same
  leading apostrophe as `=`, `+`, `-` and `@`.
