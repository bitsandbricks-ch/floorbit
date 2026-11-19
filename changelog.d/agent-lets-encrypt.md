### Added

- A hosted Floorbit with a domain for its agents gets each tenant a Let's Encrypt certificate for
  `<tenant>.agent.<domain>` and hands it to the tenant's agents, so laptops in the hall trust the
  agent's front door without installing a CA. Set the domain with `flask tenants agent-domain`;
  without one, agents keep Floorbit's own CA. The key reaches each agent encrypted to that agent's
  own key, and is replaced when an agent that had it is revoked.
