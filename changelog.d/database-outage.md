### Changed

- **Floorbit keeps running when its database is away.** Pages, the live status and the big screens keep working on what was last read; saving answers a clear "database unavailable" (in German too) instead of an error; crew pages show a banner, and everything comes back by itself, trying again after 1 s up to every 30 s. It also starts without the database instead of stopping after 30 s. `/healthz` now stays `200` and reports `"database": "down"`, so Docker and Kubernetes don't restart it in a loop; `/healthz?strict=1` gives the old `503`. See `docs/database.md`.
