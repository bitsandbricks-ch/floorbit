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
2. **Download** for about 6 seconds or 400 MB, whichever comes first. Each request is sized to
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

## Limits

Each test stream holds one of the server's threads, and the live updates need those too, so:

- at most 6 downloads or uploads run at once; a seventh seat is asked to try again in a minute;
- each client IP may move 2 GB in 10 minutes (a test moves at most about 800 MB, plus the first
  request of each direction);
- each client IP may save 10 results in 10 minutes.

The test endpoints need the seat's signed help link, like the help page.

## API

All under the seat's signed link (`?k=<signature>`), without an account:

- `GET /help/<seat>/speed/ping`: an empty answer.
- `GET /help/<seat>/speed/down?bytes=`: that many random bytes (at most 200 MB).
- `POST /help/<seat>/speed/up`: the body is read and dropped (at most 24 MB).
- `POST /help/<seat>/speed/result`: `{"down_mbps", "up_mbps", "ping_ms", "jitter_ms"}`.

The speed test is part of the **helpdesk** feature (Settings > Features).
