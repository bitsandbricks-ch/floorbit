### Added

- Port actions: **Bounce port** on a seat in the floor plan takes its switch port down for a few
  seconds and brings it back. Needs `ports.act` and a port actions plugin. The built-in SSH port
  actions plugin uses the tech's own switch login for each action and never stores it, pins switch
  host keys on first use, and knows Cisco IOS/NX-OS, Aruba AOS-CX/ProCurve and Junos. Every attempt
  is in the audit log. See `docs/ports.md`.
- **Flag for a tech** on a seat files a "Tech visit" incident with a note.
- New plugin area `ports`; the demo data pretends to bounce ports.
- New dependency: `paramiko` (SSH).
