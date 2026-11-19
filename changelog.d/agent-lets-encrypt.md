### Added

- Each tenant gets a Let's Encrypt certificate for `<tenant>.agent.<domain>` and hands it to the
  tenant's agents, so laptops in the hall trust the agent's front door without installing a CA. The
  domain comes from Floorbit's own address, and the certificate is ordered by itself once public DNS
  and port 80 reach Floorbit; until then each agent's page says what is missing.
  `flask tenants agent-domain` sets another domain or `off`. The key reaches each agent encrypted to that agent's
  own key, and is replaced when an agent that had it is revoked.
