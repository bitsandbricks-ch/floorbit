### Changed

- The Kubernetes manifest sets `CHECKIN_TRUST_PROXY=true`, since only its Ingress reaches the pod.
  Before, every visitor looked like Traefik: five wrong passwords from anyone locked that username
  for everyone, and check-ins couldn't tell seats apart.

### Added

- Floorbit logs a one-time `[proxy]` hint when requests come through a proxy that it doesn't trust
  (`X-Forwarded-For` set, `CHECKIN_TRUST_PROXY` off). The reverse proxy section of the install
  guide now covers the setting.
