# Switch commands

The **Commands** page (`/commands`) runs a saved command on one or many switches and shows the
answers side by side: the status of one port on the access switches of a row, the MAC address
table of two switches, or the software version of every switch before doors open.

Code: [`floorbit/commands.py`](../floorbit/commands.py) (templates, checks, running),
[`floorbit/blueprints/commands.py`](../floorbit/blueprints/commands.py),
[`frontend/src/pages/Commands.tsx`](../frontend/src/pages/Commands.tsx).

## Turning it on

It uses the same plugin as [port actions](ports.md): turn on **SSH port actions** under
*Settings > Plugins* and pick the switch software there (Cisco IOS, NX-OS, Aruba AOS-CX, ProCurve
or Junos). With the demo data on, the page answers with made-up output and touches nothing. The
feature can be turned off under *Settings > Features* (`commands`); it also goes off with port
actions.

## Nobody types a command

The crew picks a **template**, the switches (up to 20) and, for templates about one port, the port.
The command that goes to the switch is shown before it runs. Templates come in two kinds:

| Kind | Who | What it may be |
| --- | --- | --- |
| Show | Accounts with `ports.act` (admin, lead, tech) | Every command starts with `show`, `display`, `ping`, `traceroute` or `get`: it only reads. |
| Change | Accounts with `commands.change` (admin, lead) | Anything. The page and the API ask a second time before it runs. |

Built in, with the right words for each switch software:

| Template | Kind | Cisco IOS |
| --- | --- | --- |
| Port status | show | `show interface {port}` |
| All ports | show | `show interfaces status` |
| MAC address table | show | `show mac address-table` |
| MAC addresses on a port | show | `show mac address-table interface {port}` |
| Port errors | show | `show interfaces counters errors` |
| Software version | show | `show version` |
| Clear port counters | change | `clear counters {port}` |

Admins add their own under **New command**: a name, an id, the kind and up to 10 commands, one per
line. `{port}` is the only placeholder. A show template whose commands don't start with one of the
words above is refused: make it a change template instead. Custom templates are kept in
`data.json` under `command_templates`.

The port the crew types is checked like a port action's (`Gi1/0/3`, `ethernet1/1/12`, `xe-0/0/1.0`):
nothing else can ride along. Switches must be in the inventory with a management IP.

Accounts with `terminal.open` get a button on each answer that opens a [terminal](terminal.md) on
that switch. A link can fill the form: `/commands?template=port_status&switch=sw-a-01&switch=sw-a-02&port=Gi1/0/3`.

## The login

The plugin asks for the tech's own switch username and password, like a port action. They are used
for the connections of that one run (one per switch, at most 8 at a time) and dropped: never
stored, logged or sent anywhere else. Five failed logins in 15 minutes pause the account, shared
with port actions. Host keys are pinned as described in [ports.md](ports.md). One action at a time
per switch: a switch that is busy with a port action answers "still running".

## Audit

Every run is in the [audit log](audit.md), one line per switch ("Ran Port status", the switch and the
port), failed ones too. The output is not: it can name MACs and IPs.

## API

`GET /api/commands`: the templates the account may run (with their commands for the plugin's switch
software), the switches and whether a login is needed. Needs `ports.act`.

`POST /api/commands/run` with `{template, switches, port, username, password}` answers
`{label, commands, results: [{switch, ok, output, error, ms}]}`. A change template answers 409 with
`confirm: true` until the request has `confirm: true`. Output is cut at 64 KB per switch.

`PUT /api/commands/templates/<id>` with `{label, kind, commands}` and `DELETE` on the same path:
admins only (`settings.manage`).

A plugin other than SSH port actions can run commands too: see `send_commands` under
[the ports area](plugins.md#areas-uses).
