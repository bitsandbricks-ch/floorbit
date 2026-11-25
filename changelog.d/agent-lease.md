### Added

- Two agents for the same tags back each other up with nothing to set up: Floorbit picks the one that polls the devices and logs in to them, and hands that role to the other agent within a second when the first one's link closes. VRRP is now only needed to move addresses. Agents in one group also share their certificate names.

### Fixed

- A LibreNMS alert raised through one agent and cleared through the other agent of the same group no longer stays open, and LibreNMS posting to both agents shows the alert once.
- Two agents for the same tags fetch NetBox once instead of each on its own, and the inventory lists that NetBox once.
