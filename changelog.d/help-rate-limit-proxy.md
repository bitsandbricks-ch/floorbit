### Fixed

- Behind a reverse proxy, the seat help page no longer puts every attendee in one rate limit: with
  "Behind a reverse proxy" (`CHECKIN_TRUST_PROXY`) on, it counts each client's own address.
