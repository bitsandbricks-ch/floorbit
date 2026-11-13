### Changed

- The app is now called Floorbit in the browser too (page titles, top bar, sign-in page, the
  default Discord bot name).
- Every page shows a "Buy me a coffee" and a "Powered by bitsandbricks.ch" link; the kiosk view
  shows the second one in its legend bar.
- For contributors: `app.py` is split into the `floorbit/` package (one blueprint per area of the
  API, a `sources/` layer in front of NetBox and LibreNMS), `static/js/app.js` into
  `static/js/editor/` files by feature, and changelog entries go into `changelog.d/` fragments.
  See `docs/architecture.md`.

### Fixed

- The Docker image now contains every module the app imports (the switch port view's module
  was missing from it).
