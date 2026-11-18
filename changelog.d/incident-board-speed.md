### Fixed

- The incident board opens fast with many incidents: with 300 incidents it took almost two seconds
  per refresh, now about 30 ms. Permission checks read the roles once per request instead of once
  per check.
