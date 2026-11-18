### Changed

- `LAN_ACCESS=direct` is gone: the Floorbit server never reaches the event network itself, not even
  for development. Tests and development run the plugins the way the local agent does.
- Check-in takes the seat PC's address only from the local agent's front door, hosted or
  self-hosted alike, never from the request's own address or `X-Forwarded-For`. A check-in from
  anywhere else keeps the seat and nick without an address or port, and the page asks to type the
  check-in address on the seat PC. With allowed networks set, it is refused instead.
- `docker-compose.yml` and the Kubernetes manifest turn the agent's front door on and open it on
  port 80 (`CHECKIN_PUBLISH_PORT`): point the check-in address at it in the event DNS.
