### Added

- The Cables page lists the machines on seat ports that the patch plan doesn't explain, read from the switches' MAC tables and ARP: machines with another seat's IP (swapped seats or cables) and machines on ports without a cable, which can be patched to a seat or marked as infrastructure in one click. Monitoring plugins can offer `port_clients(hostname)`; the LibreNMS plugin does.
