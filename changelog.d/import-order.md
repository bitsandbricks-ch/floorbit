### Fixed

- Importing `auth` before `floorbit` (as `tests/test_nav.py` does when run on its own) no longer fails
  with a half-initialised module: the blueprints are imported when the app is built.
