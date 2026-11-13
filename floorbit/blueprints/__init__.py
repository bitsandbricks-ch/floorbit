"""One blueprint per area of the app. A new area gets its own module, added to ALL."""
from . import cache, config, network, pages, seat_blocks, switches

ALL = [pages.bp, config.bp, switches.bp, seat_blocks.bp, cache.bp, network.bp]
