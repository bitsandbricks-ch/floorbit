### Fixed

- "Clear port counters" now clears them on Cisco IOS. IOS asks `[confirm]` first, and Floorbit used to close the connection there, so it said the counters were cleared when they weren't. A switch command that asks to confirm, or for a default in brackets (`[startup-config]?`), now gets Enter, since the tech confirmed the template already.
