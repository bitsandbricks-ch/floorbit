### Changed

- With `FLOORBIT_CLUSTER` set, the image starts one gunicorn worker per CPU the container may use
  (its CPU limit), at most 4, so busy moments (doors open, a wall of dashboards reloading) no longer
  queue behind one process. Without the cluster it stays at one worker. `GUNICORN_CMD_ARGS=--workers N`
  still picks the number. See `docs/sizing.md`.
