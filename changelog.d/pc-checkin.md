### Added

- Check in from a PC without scanning anything: each seat card shows a short address
  (`CHECKIN_ADDRESS`) and the seat's PIN. People type the PIN and their nick; the PIN names the seat.
- Each PIN check-in teaches Floorbit which switch port the seat is on (core ARP, then the access
  switches' MAC tables). That seat to port pair is kept and used wherever no cable is drawn, and the
  seat then shows the MAC and IP on its port now.
- Problems lists check-ins that disagree: two seats on one port, a port the patch plan gives to
  another seat, or a seat taken over by another nick.

### Changed

- Finding the switch port of an IP skips uplinks: of all switches that learned the MAC, the port
  with the fewest MACs wins.
