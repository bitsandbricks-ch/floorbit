### Changed

- Floorbit moves data saved by older versions to the current shape once, when it starts (and when
  a backup is restored), and records how far it got in `data_version`. The code reads one shape
  only from then on.
- Seat block groups from the classic editor become plan groups.

### Removed

- Settings > Switch logins. Logins saved there move into the inventory's SSH credentials once:
  `*` becomes the default login, a switch's name goes on that switch, and a pattern becomes a tag
  on the switches it matches now (a name that matches no switch also becomes a tag, to give to the
  switch later). `/settings/credentials` now opens the inventory. A login whose password can't be
  opened any more is dropped with a note in the log; set it again in the inventory.
