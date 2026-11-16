# Sizing for a large event

How much of Floorbit's own work grows with the number of seats, measured with
`scripts/load_test.py` (issue #473). The script builds a hall of fake switches in memory, with a PC
on every seat port, and times what Floorbit does with it. Nothing talks to LibreNMS, NetBox or
Redis, so the numbers are Floorbit's share only.

```sh
python scripts/load_test.py --seats 4000 --database sqlite --fdb-ms 1000
```

## Measured

4000 seats on 84 access switches (48 seat ports each). LibreNMS was given a pretend 1 second per MAC
table read. This ran in a 4-CPU container with Python 3.13:

| What | Files | SQLite |
| --- | --- | --- |
| Unmatched clients: read every seat switch's MAC table | 21.1 s | 21.1 s |
| Patch plan check (ports up against the cables) | 0.01 s | 0.01 s |
| Every seat checks in once, one after the other | 37.5 s (9.4 ms each) | 43.3 s (10.8 ms each) |
| Read the whole check-in history back | 0.01 s | 0.01 s |

Postgres wasn't measured. The script takes `--database files` or `sqlite`.

## What it means

- **MAC tables are the slow part, and LibreNMS sets the pace.** Floorbit reads four switches side
  by side (`WORKERS` in `floorbit/port_clients.py`), at most every two minutes, in the background.
  The page shows the last read. Floorbit's own work on 4000 seats takes under a tenth of a second.
  The rest is waiting on LibreNMS, which costs about (switches ÷ 4) × its time per MAC table.
- **The patch plan check is free.** It reads what the port watch already polled, so the seat count
  doesn't add LibreNMS calls.
- **Check-in keeps up with doors opening.** One check-in takes about 10 ms at 4000 seats, so even
  4000 people arriving in the same few minutes are a handful of seconds of work. Check-ins
  queue on one lock; none is lost.
- **Bulk reads only.** ARP is read once per seat network (a /24), and MAC tables once per switch.
  There is never one LibreNMS call per client.

Run the script again after changing check-in or the seat mapping, and update this page when the
numbers move.
