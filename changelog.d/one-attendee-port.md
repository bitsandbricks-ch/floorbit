### Changed

- The agent answers attendees, phones and the crew's seat walk-through on one port: the front door now answers the check-in note (`/.well-known/captive-portal`) and the seat walk-through's hello too. The front door is on by default on every agent, and the compose files and the Kubernetes manifest publish it on 443 and 80 (#986).
- The seat walk-through needs no setting. Opened through an agent, it knows the laptop at once. Otherwise it goes once to the check-in name, or to where browsers last reached an agent, which each agent learns by itself (#999).
- The check-in note on phones follows check-in. It shows only where the event DHCP hands out option 114.

### Removed

- The plugin "Check-in note on phones" (`captive-note`) and its port 8908: the front door does its job.
- The settings `SEAT_WALK_AGENT_URL`, `CAPTIVE_ENABLED` and the agent's `FLOORBIT_AGENT_LAN_URL` ("Address in the hall").
