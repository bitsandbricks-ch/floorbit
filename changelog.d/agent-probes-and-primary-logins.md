### Fixed

- Own checks on the Services page and the firewall range import from NetBox now run through the local agent; before, every own check failed on a hosted Floorbit.
- With two agents sharing VRRP addresses, switch terminals, commands and port actions go to the primary agent, not the standby, so a switch never sees logins from both.
