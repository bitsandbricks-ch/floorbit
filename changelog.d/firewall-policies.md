### Changed

- Firewalls: a range over several firewalls is cut into equal parts, one per firewall in their order (a /24 over four firewalls sends each quarter to its own), and the page shows where each part goes now. A range can be any span of addresses (`192.0.2.0-192.0.2.128`), not only a network. A fallback is optional and only for cores that move a part while its firewall is down. The firewall cards no longer say "Backup for".

### Removed

- Firewalls: **Split a network**. Give the range all its firewalls instead.
