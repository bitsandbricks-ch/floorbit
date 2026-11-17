### Fixed

- Behind a reverse proxy, attendees no longer share one limit. With "Behind a reverse proxy"
  (`CHECKIN_TRUST_PROXY`) on, the seat help page, the seat finder and the sign-in lockout count each
  client's own address, so one person guessing a password can't lock that account for everyone.

### Security

- Behind a reverse proxy, Floorbit took the leftmost `X-Forwarded-For` address, which the client
  can write itself: an attendee could check in with another seat's address or dodge the sign-in
  lockout. It now takes the address the proxy added (`CHECKIN_PROXY_HOPS` from the right, default 1).
