### Changed

- Firewalls: a seat range can now be any span of addresses (`192.0.2.0-192.0.2.128`), not only a network, the way the core policy-routes them. Each range names its firewall and, only where the core does that, a fallback. The firewall cards no longer say "Backup for", and **Split a network** gives each range one firewall unless you ask for fallbacks.
