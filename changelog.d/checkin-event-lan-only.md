### Changed

- Check-in only works on the event LAN: a check-in that didn't come through a local agent's front
  door, or comes from a public address outside the event's IP ranges (a hotspot, a VPN), is refused.
  The page tells the player to plug the LAN cable at their seat into their PC and open the check-in
  address there. Check-in is a tech check-in that learns the seat's IP, MAC and switch port, so such
  check-ins only made false mappings.
