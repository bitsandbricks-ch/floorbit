### Fixed

- The switch terminal works with several gunicorn workers or pods (`FLOORBIT_CLUSTER=valkey`): a
  request that lands on another worker is passed to the one holding the terminal, so its output no
  longer goes missing and no sticky sessions are needed.
