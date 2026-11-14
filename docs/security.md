# Security detection

The **Security** page (`/security`, in the top bar) lists what the security plugins see on the hall
network: **rogue DHCP servers**, **ARP spoofing** (one IP answered by several MACs), **MAC flapping**
between ports, **loops** and **broadcast storms**. Each finding points at a switch port and, where
Floorbit can tell, a seat. Active findings also show on the floor plan as a dashed amber ring on
the seat or switch, with a count next to **Security**. Code:
[`floorbit/security.py`](../floorbit/security.py) and
[`floorbit/blueprints/security.py`](../floorbit/blueprints/security.py).

## What you can do with a finding

- **Shut port** (accounts with `ports.act`, while a [port actions](ports.md) plugin is on): one
  click, plus your own switch login when the plugin needs one. The server takes the switch and
  port from the finding, not from the browser. The port stays down until someone turns it on
  again under **Ports Floorbit shut**, which lists who shut it, when and why.
- **I'm on it**: tells the others someone is looking at it. Findings someone is on sort
  below the ones nobody has taken.

A finding the plugin stops reporting is cleared and stays under **Cleared in the last hour**.
If a plugin fails, its findings stay as they were: a failed check doesn't clear anything.

## Where findings come from

Floorbit detects nothing itself: a plugin with `uses: [security]` does. Today:

- **Demo data** reports an ARP spoof, a flapping MAC, a broadcast storm and, three minutes in
  every six, a rogue DHCP server, so the page, alerts and shutdown can be tried.
- Your own plugin: a DHCP probe, a switch syslog reader (DHCP snooping, port security, STP
  topology changes), or your monitoring system.

`security_findings()` returns what the plugin sees right now:

```python
[{"id": "arp-192.0.2.10", "kind": "arp-spoof", "severity": "high",
  "title": "192.0.2.10 is answered by two MACs", "detail": "...",
  "switch": "sw-b-01", "port": "Gi1/0/4", "mac": "02:00:00:00:00:1b", "ip": "192.0.2.10",
  "evidence": ["02:00:00:00:00:1b on Gi1/0/4", "02:00:00:00:00:2c on Gi1/0/9"]}]
```

| Key | |
| --- | --- |
| `id` | stable while it is the same problem (Floorbit puts the plugin id in front) |
| `kind` | `rogue-dhcp`, `arp-spoof`, `mac-flap`, `loop`, `storm` or `other` |
| `severity` | `high`, `medium` (the default) or `low` |
| `title`, `detail` | up to 120 and 500 characters, shown as text |
| `switch`, `port` | where it is; needed for **Shut port** |
| `mac`, `ip`, `seat` | Floorbit finds the seat from the seat mapping by MAC (the device at fault), or by IP when there is no MAC, unless `seat` is given |
| `evidence` | up to 10 short lines |

## Polling and alerts

A background thread asks every security plugin every **Security check interval** seconds (60,
`SECURITY_INTERVAL`, **Settings › Health wall and security**). A new finding publishes
`security.finding`, which updates the floor plan and the page, runs plugin hooks and, for **high**
and **medium** findings, posts to Discord (**Security alerts**, `DISCORD_SECURITY_ALERTS`). **Mention
on outage** is put in front of high ones only. The first round after a start only records what is
there.

## Personal data

Findings name MACs and IPs, so the page and its API need `seats.view` (Tech, Lead, Admin; not
Viewer or Kiosk). Discord messages and the live event every open browser gets say only what and
where: kind, severity, switch, port and seat. They never include the MAC, IP or title.

| | Needs |
| --- | --- |
| See findings, mark "I'm on it" | `seats.view` |
| Shut a port, turn it on again | `ports.act` |
| **Check now** | `plugins.run` |
