### Changed

- The seat walk, the row walk, patching and the cable check now work per row, not per block. You pick rows by name ("C", or "A 2" in a block numbered as a whole) from one shared picker, grouped by block. Patching takes several rows in the order picked, even from different blocks (#1057).

### Fixed

- Blocks named by their rows (C, D, …) showed a dash in the block pickers and a "?" in the power circuits. They now show their row letters, such as "C–D", and a circuit fed by rows reads "rows C, D" (#1003).
- The cable check no longer lists uplinks as "up with no cable": ports on a topology link, with an LLDP/CDP neighbour, or matching the uplink pattern are left out (#1046).
