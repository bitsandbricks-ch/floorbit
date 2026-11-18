### Changed

- Speed tests at the seat have limits you can set under **Settings > Speed tests**: on or off
  (`SPEEDTEST`), streams at once (`SPEEDTEST_MAX_RUNNING`, 3 instead of 6), data per test
  (`SPEEDTEST_TEST_MB`, 250 MB instead of about 800 MB), one test per seat every
  `SPEEDTEST_SEAT_MINUTES` (10) and a speed cap per stream (`SPEEDTEST_MAX_MBPS`, 1000 Mbit/s).
  A seat that tested lately is told how long to wait. See `docs/speedtest.md`.
