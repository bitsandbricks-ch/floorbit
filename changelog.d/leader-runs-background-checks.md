### Changed

- With several pods or workers, only the leading one runs the background checks (switch status,
  ports and traffic, health, security, power, services, game servers, DNS); the others show what
  it saw, and a new leader carries on from it instead of starting over.
