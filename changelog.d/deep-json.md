### Fixed

- A request body nested hundreds of levels deep (`[[[[…`) is refused with "The JSON is nested too
  deeply." instead of an internal error, signed in or not, and an uploaded icon of groups inside
  groups is refused the same way.
