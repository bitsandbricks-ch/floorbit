### Added

- Shelly and Home Assistant meters for Electrics: two plugins the local agent runs in the hall. They
  read the load from Shelly plugs, relays and energy meters, or from Home Assistant power sensors,
  and hand it to the circuits by meter id. A refused password or token is not tried again until a
  tech clears it. See docs/power.md.
