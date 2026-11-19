### Fixed

- Telemetry: Catalyst MAC tables are read only for the VLANs the switch itself lists, so a VLAN it doesn't have no longer times out every minute.
- Telemetry: a VLAN or table that doesn't answer is named in the problem ("no answer for VLAN 30", "while reading fb_bridge") instead of blaming the login or ACL, and no longer reappears in the agent's log every minute.
- Telemetry: a device whose one VLAN or table doesn't answer no longer counts as a failing device on the agent; a device that goes silent altogether is still reported next to it.
- Telemetry: NX-API, RESTCONF and OPNsense API errors say why ("Connection refused", "Name or service not known") instead of only "ConnectionError", and a wrong name counts as "no route".
- Telemetry: traps-only devices are no longer reported as silent every minute.
