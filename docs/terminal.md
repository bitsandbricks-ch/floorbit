# Switch terminal

The **Switch terminal** page (`/terminal`) opens a terminal on one switch in the browser: the
switch's own CLI, for what the saved [switch commands](commands.md) don't cover. Open it from the
Commands page, or link to it with `/terminal?switch=sw-a-01`.

The page is a workspace: one tab per open terminal, named after its switch with a dot that says
whether it is still connected, and a **New** tab with the form that opens another. The terminal
fills the page below the tabs; a tab you leave keeps running and keeps its scrollback. The **x** on a
tab closes that terminal. When a switch hangs up, its tab stays with the reason until you close it.
The terminal is dark in both themes.

Code: [`floorbit/terminal.py`](../floorbit/terminal.py),
[`floorbit/blueprints/terminal.py`](../floorbit/blueprints/terminal.py),
[`frontend/src/pages/Terminal.tsx`](../frontend/src/pages/Terminal.tsx) (with
[xterm.js](https://xtermjs.org/)).

## Who can open one

Accounts with `terminal.open`: admins and leads by default. Give it to a custom role on *Settings >
Roles and teams*. The plugin is the same as for [port actions](ports.md): turn on **SSH port
actions** under *Settings > Plugins*. With the demo data on, the terminal is a pretend switch that
knows a few show commands and touches nothing. The feature can be turned off under *Settings >
Features* (`terminal`); it also goes off with port actions.

## The login

The tech types their own switch username and password, or the [stored login](credentials.md) for
that switch is used. Either opens the one SSH connection and is
dropped: never stored, logged or sent anywhere else. Failed logins count toward the same pause as
port actions (five in 15 minutes). Host keys are pinned as described in [ports.md](ports.md).

## Several workers or pods

The SSH connection lives in the worker (or pod) that opened the terminal. With
`FLOORBIT_CLUSTER=valkey` ([sizing](sizing.md#more-than-one-worker), [Kubernetes](kubernetes.md)),
each one lists its open terminals in Valkey, and a request that lands on another worker is passed
to the one that holds the terminal, sealed like the agent's calls: what the tech types never sits
in Valkey in the clear. The limits (10 terminals, 3 per account) count every worker's. When a worker
or pod stops, its terminals close with it.

## What is recorded

Every line the tech sends is in the [audit log](audit.md), with their name and the switch
("Typed", `sw-a-01: show running-config`), as typed: a line finished with tab completion is logged
as far as it was typed. A line typed while the switch asks for a password (`Password:`, `Enable
secret:`) is logged as hidden. Opening and closing are logged too, with the reason it closed. What
the switch prints is not logged: it can name MACs and IPs.

## Limits

| Setting | Default | What it does |
| --- | --- | --- |
| `TERMINAL_IDLE_MINUTES` | `10` | Close a terminal after this long without typing. |
| `TERMINAL_MAX_MINUTES` | `60` | Close it after this long in all. |

At most 3 terminals per account and 10 in all are open at once. Leaving the page doesn't close a
terminal right away: coming back (or a reload) brings your open terminals back as tabs.

## API

- `GET /api/terminal`: whether a terminal can open, the switches and your open terminals.
- `POST /api/terminal` with `{switch, username, password, cols, rows}` answers `{id}` (201).
- `GET /api/terminal/<id>/output?after=n`: the output after character `n`, waiting up to 20 s for
  some: `{data, next, closed}`. `closed` says why it ended.
- `POST /api/terminal/<id>/input` with `{data}`; `POST /api/terminal/<id>/resize` with `{cols, rows}`;
  `DELETE /api/terminal/<id>`.

A terminal belongs to the account that opened it; anyone else gets 404. Sessions live in the app's
memory, which works with the image's single gunicorn worker.
