### Added

- DHCP lease lines in the syslog (ISC dhcpd, Kea, dnsmasq, MikroTik) are an IP to MAC source: check-in,
  the seat walk and the IP search know a new laptop the moment it gets its address, before the next
  ARP poll (#520).
- A DHCP server that runs out of addresses ("no free leases" and the like in its syslog) shows up as a
  needs-attention item on the Problems page.
