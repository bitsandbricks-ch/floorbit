### Changed

- With several pods or workers, only the leading one asks for the switch status; the others show
  what it saw, and a new leader carries on from it instead of starting over.
