### Fixed

- Open pages no longer stay out of date after their live connection dropped (Wi-Fi, a restart)
  or, with several pods, after Redis was away for a while: they fetch everything again as soon as
  the connection is back.
