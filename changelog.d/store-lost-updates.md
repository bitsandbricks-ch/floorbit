### Fixed

- Two saves at once no longer undo each other. A background task (game server checks, power, links,
  schedules) that saved its part of the data a moment after a crew member changed something else
  could put the old state back, so an incident marked fixed could show as open again. Each save
  now keeps the parts it didn't change as they are.
