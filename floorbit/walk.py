"""Walking the row (issue #473): the crew plugs a laptop in at one seat after the other, and Floorbit
says which port of the switch just came up, so each seat's port is known in seconds.

Two ways to see a port come up:

- **Syslog** (``floorbit/syslog.py``, or relayed by the agent): the switch says so the moment it
  happens. The lines are matched by device and by the usual link-up wording of Cisco, Aruba,
  Juniper and MikroTik.
- **Polling**: the monitoring source's port list, compared with the ports that were up when the
  walk began. LibreNMS only learns this when it polls the switch, so it can take minutes; the
  page says which way it is watching.
"""
import re
import threading
import time
from collections import OrderedDict

from . import cables as cables_mod
from . import sources

LINK_UP = re.compile(r'changed state to up|\blink up\b|LINK_?UP\b|is now on-line|link status:? up', re.I)
POLL_EVERY = 5          # seconds: the port list of one switch is read at most this often
MAX_WALKS = 100         # baselines kept (one per switch and start)


class Walks:
    def __init__(self):
        self._lock = threading.Lock()
        # (switch lowercase, since) -> (ports up when the walk began, {port: when the poll first saw it up})
        self._baselines = OrderedDict()
        self._polled = {}                 # switch lowercase -> (at, {canonical port: name} that are up)

    def _up_now(self, switch, now):
        key = switch.lower()
        with self._lock:
            hit = self._polled.get(key)
            if hit and 0 <= now - hit[0] < POLL_EVERY:
                return hit[1]
        from .syslog import canonical_port
        ports = sources.monitoring().device_ports(switch) or []
        up = {canonical_port(p['name']): p['name'] for p in ports if p.get('name') and p.get('state') == 'up'}
        with self._lock:
            self._polled[key] = (now, up)
        return up

    def ups(self, switch, since, receiver=None, now=None):
        """Ports of ``switch`` that came up since ``since``: ``[{"port", "at", "how"}]``, newest first,
        one row per port."""
        from .syslog import canonical_port
        now = time.time() if now is None else now
        names = {canonical_port(c['port']): c['port'] for c in cables_mod.all_cables()
                 if c['switch'].lower() == switch.lower()}
        up = self._up_now(switch, now)
        found = {}
        for line in (receiver.search(device=switch, limit=2000) if receiver is not None else []):
            if line['ts'] < since or not line.get('port') or not LINK_UP.search(line.get('message') or ''):
                continue
            port = line['port']
            if port not in found:      # newest first: the first line is the latest
                found[port] = {'port': names.get(port) or up.get(port) or port, 'at': line['ts'], 'how': 'syslog'}
        key = (switch.lower(), since)
        with self._lock:
            if key not in self._baselines:
                self._baselines[key] = (set(up), {})
                while len(self._baselines) > MAX_WALKS:
                    self._baselines.popitem(last=False)
            before, seen = self._baselines[key]
            for port in up:
                if port not in before:
                    seen.setdefault(port, now)
            seen = dict(seen)
        for port, at in seen.items():
            if port in up and port not in found:
                found[port] = {'port': names.get(port, up[port]), 'at': at, 'how': 'poll'}
        return sorted(found.values(), key=lambda r: -r['at'])


walks = Walks()
