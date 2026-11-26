# Speedtest at the seat

The seat's help page (the QR code on each seat, see [incidents.md](incidents.md)) has a
**Test your connection** button. It measures latency, download and upload between the player's
machine and the Floorbit server, which proves (or rules out) "it's the network" inside the hall.
Issue #99.

It is not an internet speed test. It shows what the hall's network gives a seat up to the server,
so run Floorbit on a host with a fast link into the core for the numbers to mean much.

## How it runs

The test runs in the browser, needs no account and takes about 20 seconds:

1. **Latency:** 11 small requests. The first one opens the connection and isn't counted; the
   median of the rest is the latency, and the mean change between them is the jitter.
2. **Download** for about 6 seconds or half of **Data per test** (see [Limits](#limits)), whichever
   comes first. Each request is sized to
   take about 1.5 seconds (1 to 200 MB of random bytes, so nothing on the way can compress them).
   The first request only finds the size.
3. **Upload** the same way, 1 to 24 MB per request.
4. The numbers are sent back and kept for the seat.

The page shows the result. It goes on the seat's open helpdesk incident, and a report filed
within 30 minutes of a test carries it too. The incident board shows it under the report:

> Speed test at the seat, 2 min ago: 912 down, 455 up Mbit/s, 1.2 ms

## What is kept

For each seat: download and upload in Mbit/s, latency and jitter in ms, and when. That's all: no IP
address, browser or name. The last 5 results per seat are kept in `data.json` (`speedtests`). The
crew can read them at `GET /api/speedtests?seat=` (`incidents.work`).

## Side by side per switch

The **Speed tests** widget (on the ready-made Traffic dashboard, for accounts with **Work
incidents**) puts the results next to each
other, so a switch or uplink that is slow for every seat on it shows up as one row instead of many
separate "slow" reports. It takes each seat's latest test of the last 12 hours and shows:

- the hall: seats tested and the median download, upload and ping;
- one row per switch (from the port reads, as on the floor plan): seats tested, the medians, and
  each seat with its download, slowest first, linking to the seat on the floor plan;
- **Slow** on a switch whose median download is under half the hall's, with at least
  2 seats tested (one slow seat is that seat, not the switch). Those rows come first;
- seats no switch is known for, in a list of their own.

It updates when a new result comes in. `GET /api/speedtests/summary` has the same.

## Limits

Every test streams from the Floorbit server, holds one of its threads while it runs (the live
updates need those too), and moves a lot of data. **Settings > Speed tests** caps it:

| Setting | Environment | Default | What |
| --- | --- | --- | --- |
| Speed test on the help page | `SPEEDTEST` | on | Off hides the button on the help page and refuses every test. |
| Streams at once | `SPEEDTEST_MAX_RUNNING` | 3 | Downloads and uploads running at once, over all seats. One more is asked to try again in a minute. |
| Data per test | `SPEEDTEST_TEST_MB` | 250 MB | What one test may move, download and upload together. The page stops each direction at about half of it, so a gigabit seat still measures in full. |
| One test per seat every | `SPEEDTEST_SEAT_MINUTES` | 10 minutes | A seat that tested lately is told how many minutes to wait. 0 for no limit. |
| Speed cap per stream | `SPEEDTEST_MAX_MBPS` | 1000 Mbit/s | The server never sends or reads one stream faster than this. 0 for no cap. |

With the defaults, the tests together never move more than 3 Gbit/s, and a hall can't keep the
server busy with tests. On top of that:

- each client IP may move four tests' worth in 10 minutes (for the crew testing seat after seat
  from one laptop);
- each client IP may save 10 results in 10 minutes.

The test endpoints need the seat's signed help link, like the help page.

## API

All under the seat's signed link (`?k=<signature>`), without an account:

- `GET /help/<seat>/speed/ping`: an empty answer.
- `GET /help/<seat>/speed/down?bytes=`: that many random bytes (at most 200 MB, and at most half of
  **Data per test**).
- `POST /help/<seat>/speed/up`: the body is read and dropped (at most 24 MB).

They answer 404 while speed tests are off. The help page's `GET /api/helpdesk/seats/<seat>` says
`"speedtest": {"test_mb": 250}`, or `null` while they are off.
- `POST /help/<seat>/speed/result`: `{"down_mbps", "up_mbps", "ping_ms", "jitter_ms"}`.

The speed test is part of the **helpdesk** feature (Settings > Plugins > Built in).
