"""One blueprint per area of the app. A new area gets its own module, added to ALL."""
from . import audit, backup, cache, config, inventory, network, pages, plugins, seat_blocks, seat_map, switches

ALL = [pages.bp, config.bp, switches.bp, seat_blocks.bp, cache.bp, network.bp, backup.bp, audit.bp, plugins.bp,
       inventory.bp, seat_map.bp]
