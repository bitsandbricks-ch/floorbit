### Fixed

- The seat speed test no longer locks up after a few HEAD requests or downloads cut off before the
  first byte. Each one used to keep a test slot for good, so after six of them every seat got "Other
  seats are testing right now" until Floorbit restarted.
