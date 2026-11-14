"""One blueprint per area of the app. A new area gets its own module, added to ALL."""
from . import (
               audit,
               backup,
               cache,
               config,
               demo,
               health,
               incidents,
               inventory,
               network,
               pages,
               plugins,
               ports,
               power,
               problems,
               seat_blocks,
               seat_map,
               security,
               setup,
               stats,
               switches,
)

ALL = [pages.bp, config.bp, switches.bp, seat_blocks.bp, cache.bp, network.bp, backup.bp, audit.bp, plugins.bp,
       inventory.bp, seat_map.bp, demo.bp, incidents.bp,
       health.bp, ports.bp, security.bp, power.bp, problems.bp, setup.bp, stats.bp]
