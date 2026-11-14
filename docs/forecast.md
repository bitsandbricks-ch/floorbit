# Bandwidth forecast

The Stats page shows what the hall's bandwidth will probably do in the next 12 hours. If you set
the line's capacity, Floorbit warns before the line is expected to fill: on the Problems list, on
Discord and as a webhook.

## How it's worked out

Simple on purpose, so anyone can check it. From the [stats](stats.md) Floorbit keeps the busiest
read of every hour since the event started (the same rows as the [report](report.md)).

1. **Profile.** For each hour of the day, the average busiest read at that hour on the event's
   earlier days. An hour of the day the event hasn't seen yet uses the average of the last 3
   hours.
2. **Level.** How the last 3 hours ran against the profile for those hours. 1.2 means 20 % busier
   than on earlier days. It's kept between half and double.
3. **Forecast.** Profile times level for each of the next 12 hours, with a range from the quietest
   to the busiest earlier day at that hour.

The page says which of these it used ("from 2 days of this event; the last 3 hours ran 20 %
busier"). A forecast needs 6 hours of history. **New event** on the report starts the history
again.

The numbers are the hall's total: every access port, the LAN cache's traffic included. So they're
an upper bound for what the internet line carries. If most downloads come from the cache, set the
capacity a bit higher than the line or raise the warning share.

## Warnings

Set `FORECAST_CAPACITY_MBPS` to the line's capacity (for example `10000` for 10 Gbit/s). When an
hour within `FORECAST_LEAD_HOURS` (3) is expected at or over `FORECAST_WARN_PERCENT` (80 %) of it,
Floorbit:

- puts it on the [Problems](alerts.md) list (amber, red at 100 %);
- posts once per expected peak to Discord (`DISCORD_FORECAST_ALERTS`, on by default);
- sends the `forecast.alert` [webhook](api.md#webhooks).

The forecast is checked every 5 minutes.

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `FORECAST_CAPACITY_MBPS` | `0` | The line's capacity in Mbit/s. `0`: show the forecast, but don't warn. |
| `FORECAST_WARN_PERCENT` | `80` | Share of the capacity that warns. |
| `FORECAST_LEAD_HOURS` | `3` | How far ahead a forecast warns. |
| `DISCORD_FORECAST_ALERTS` | `true` | Post forecast warnings to Discord. |

The feature switch is **Bandwidth forecast** (Settings > Features).

## API

`GET /api/forecast` answers `ready`, `points` (`t`, `bps`, `low`, `high`, `basis`: `profile` or
`recent`, and `pct` with a capacity), `alert`, `level`, `days`, `peak`, `history_hours` and the
settings above.
