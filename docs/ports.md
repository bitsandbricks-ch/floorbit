# Port actions

Techs can **bounce a seat's switch port** (take it down for a few seconds, then bring it back)
from the floor plan, and **flag a seat for a tech**. Code: [`floorbit/ports.py`](../floorbit/ports.py),
[`floorbit/blueprints/ports.py`](../floorbit/blueprints/ports.py) and the plan's seat inspector
([`Inspector.tsx`](../frontend/src/pages/plan/Inspector.tsx)).

## On the floor plan

Select a seat. Under **Switch port**:

- **Bounce port** (accounts with `ports.act`, while a port actions plugin is on) asks for your
  own switch username and password, then takes the port down and up again. The player loses
  their connection for those seconds. The same button is on a seat's open incident on the
  [incident board](incidents.md#the-board).
- **Flag for a tech** (accounts that see the incident board) files an incident "Tech visit" for
  the seat, with your note. It shows on the [incident board](incidents.md) and as a red ring on
  the seat. Clear it there by marking it fixed.

## Shutting a port for a security finding

On the [Security](security.md) page, **Shut port** takes a finding's port down until someone turns
it on again (**Ports Floorbit shut**, with who, when and why). The browser only names the
finding; the server takes the switch and port from it.

Shut and bounce refuse an uplink: a port a topology link ends on, a port where LLDP or CDP sees
another device, or one whose name matches the uplink pattern (`STATS_UPLINK_PATTERN`). Taking it
down would cut every seat behind the switch, so that work goes through the switch terminal.
Turning a port on is always allowed.

## How it reaches the switch

Floorbit doesn't talk to switches itself: a plugin with `uses: [ports]` does, one at a time.

- **SSH port actions** (built in, off until an admin turns it on under **Settings › Plugins**)
  logs in to the switch's management IP over SSH and runs the commands for its **Switch
  software**: Cisco IOS, Cisco NX-OS, Aruba AOS-CX, Aruba ProCurve, Junos, or your own **Custom**
  lists (`{port}` is the interface). It changes only the running state and never saves the
  configuration.
- **Demo data** pretends: the port shows as down for 10 seconds.

With a [local agent](agent.md#switch-logins-through-the-agent) enrolled, the SSH connection is
opened by the agent in the hall; everything else on this page stays the same.

A plugin defines `port_login()` (true when it needs the tech's login), `bounce_port(target)` and
`set_port(target)`, where `target` is `{switch, host, port, model, login}` (plus `enabled` for
`set_port`) and `login` is `{username, password}` or None.

## Secure by design

- **Your login, or the stored one.** A typed password is sent with the action over HTTPS, used for
  that one SSH connection and dropped. It is never stored, logged, put in the audit log or in an
  error. An admin can store switch logins instead ([credentials.md](credentials.md)): encrypted,
  write-only, opened only for the one connection, and each use is in the audit log. A typed login
  still wins over a stored one, and a wrong stored password doesn't pause the tech's account.
- **Floorbit picks the port.** For a seat, the server finds the switch and port through the seat
  mapping and the monitoring source; the browser can't name another one. The switch must be in
  the [inventory](inventory.md) with a management IP, and port names that aren't plain interface
  names (`Gi1/0/3`, `1/1/12`, `xe-0/0/1`) are refused before anything is sent.
- **Pinned host keys.** The first connection to a switch pins its SSH host key (turn off **Trust a
  switch's key the first time** to allow only keys pinned already). A changed key stops the
  action. After replacing a switch, an admin uses **Forget pinned host keys**; **Pinned host
  keys** lists them.
- **Limits.** One action at a time per switch, the same port at most once every 30 seconds, and
  after 5 refused switch logins in 15 minutes the account waits.
- **Audit.** Every bounce, and every failed attempt, is in the audit log under **Ports** with the
  account, switch and port.

| | Needs |
| --- | --- |
| Bounce, shut or turn on a port (`POST /api/ports/bounce`, `/shutdown`, `/enable`) | `ports.act` (Tech, Lead, Admin) |
| Flag a seat for a tech | `incidents.work` (see [incidents.md](incidents.md)) |
| Turn the plugin on, pick the switch software, forget host keys | `settings.manage` |
