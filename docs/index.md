# Floorbit

The event's network on a floor plan. Place switches and seat blocks on a map of the hall, pull the
switches from NetBox, see their live status and ports from LibreNMS (or another monitoring source),
and find which switch port each seat is plugged into. Around that, Floorbit runs the crew's event:
incidents and a helpdesk at the seat, dispatch and handovers, health, security and power, and a
report when it's over.

These pages are for people running Floorbit at their own LAN.

## Start here

1. [Install with Docker Compose](install.md): the image, Redis, a reverse proxy, backups and updates.
2. [Sign-in, roles and teams](auth.md): accounts, an identity provider (OIDC) and who may do what.
3. [Inventory](inventory.md) and [halls](halls.md): your switches and the hall plan.
4. [Seat mapping](seat-mapping.md): which port each seat is on.
5. [Feature switches](features.md): turn off what your event doesn't use.

No network to try it on? [Demo mode](demo.md) fills a made-up hall.

## Build on it

- [Plugins](plugins.md): monitoring sources, health checks, actions and dashboard tiles.
- [The API](api.md): tokens, versions and webhooks, and the [API reference](api-reference.md),
  written from the code.

Floorbit is open source (AGPL-3.0) on [GitHub](https://github.com/bitsandbricks-ch/floorbit), by Mike
at BitsAndBricks.
