### Fixed

- Behind a reverse proxy, attendees no longer share one limit. With "Behind a reverse proxy"
  (`CHECKIN_TRUST_PROXY`) on, the seat help page, the seat finder and the sign-in lockout count each
  client's own address, so one person guessing a password can't lock that account for everyone.
