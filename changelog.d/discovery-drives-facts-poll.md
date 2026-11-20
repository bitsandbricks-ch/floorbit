### Changed

- What a device is (model, serial, optics, addresses, VLANs, routes) is read by SNMP as often as the
  discovery action that uses it runs, for that kind of device, instead of every five minutes: optics
  and the chassis hourly by default, an action that is off isn't read at all. Less SNMP load on the
  switches; the live views (ports, MAC, ARP, neighbours, PoE) keep their own fast clocks.
