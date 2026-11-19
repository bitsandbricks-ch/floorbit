### Fixed

- Telemetry: Catalyst MAC tables are read only for the VLANs the switch itself lists, so a VLAN it doesn't have no longer times out every minute.
- Telemetry: a VLAN or table that doesn't answer is named in the problem ("no answer for VLAN 30", "while reading fb_bridge") instead of blaming the login or ACL, and no longer reappears in the agent's log every minute.
