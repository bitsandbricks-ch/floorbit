### Fixed

- The health wall, power, DNS, security, LAN cache, forecast and "needs attention" checks keep
  running when reading their settings fails once. Started before the database answered, the health
  wall stopped for good and checked nothing until Floorbit was restarted.
