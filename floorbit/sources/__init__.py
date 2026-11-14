"""Where live network data comes from.

``monitoring()``: switch status, port counters, and which switch port an IP is on. The answer
comes from the monitoring plugin that is on (the built-in LibreNMS plugin,
``floorbit/builtin_plugins/librenms``), so nothing in the core talks to an NMS directly.
``use()`` swaps in another source (a local agent feeding a hosted instance, a fake in tests).
See docs/architecture.md.

Which devices exist is the inventory's job (``floorbit/inventory.py``), fed by plugins such as
NetBox (``floorbit/builtin_plugins/netbox``).
"""
import json
import re
import threading
import time

from . import lastgood

# Set by floorbit.plugins.init_plugins; None until the app is created.
registry = None
_override = None

# Is the monitoring source answering? Set by the status monitor's polls and by failed calls.
_health_lock = threading.Lock()
_health = {'source': None, 'ok': True, 'offline_since': None, 'last_ok': None, 'error': None}


def health():
    with _health_lock:
        return dict(_health)


def mark_ok(source):
    """Returns how long the source was down (seconds), or None if it wasn't."""
    with _health_lock:
        was_down = _health['offline_since']
        _health.update(source=source, ok=True, offline_since=None, last_ok=time.time(), error=None)
    return time.time() - was_down if was_down else None


def mark_failed(source, error):
    """Returns True when this is the start of an outage."""
    with _health_lock:
        starting = _health['offline_since'] is None
        _health.update(source=source, ok=False, error=str(error)[:300],
                       offline_since=_health['offline_since'] or time.time())
    return starting


def offline():
    with _health_lock:
        return _health['offline_since'] is not None


def _stale(entry):
    """A cached answer, marked so pages can grey it out and say how old it is."""
    at, value = entry
    out = dict(value) if isinstance(value, dict) else {'value': value}
    out.update(stale=True, as_of=at, offline_since=health()['offline_since'])
    return out


def normalise_mac(mac):
    """aa:bb:cc:dd:ee:ff, or None when it isn't a MAC."""
    hexchars = re.sub(r'[^0-9a-fA-F]', '', str(mac or '')).lower()
    if len(hexchars) != 12:
        return None
    return ':'.join(hexchars[i:i + 2] for i in range(0, 12, 2))


class NoMonitoring:
    """No monitoring plugin is on: everything reads as unknown."""
    name = None
    label = 'Monitoring'

    def enabled(self):
        return False

    def devices(self):
        return []

    def device_details(self, hostname):
        return {'status': 'unknown', 'message': 'No monitoring plugin is on'}

    def resolve_ip(self, ip_address, search_device=None):
        return None

    def port_stats(self, hostname, interface):
        return None

    def arp(self, query):
        return []

    def mac_for_ip(self, ip):
        return None

    def ip_for_mac(self, mac):
        return None


class PluginMonitoring(NoMonitoring):
    """A monitoring plugin, called through the registry (so errors land in the plugin's log)."""

    def __init__(self, registry, spec):
        self._registry = registry
        self._spec = spec
        self.name = spec.id
        self.label = spec.name

    def _call(self, method, *args):
        return self._registry.call(self._spec, method, *args)

    def enabled(self):
        from ..plugins.base import PluginError
        try:
            return bool(self._call('configured'))
        except PluginError:
            return False

    def _key(self, method, *args):
        return f'{self.name}:{method}:{json.dumps(args, default=str)}'

    def devices(self):
        # Errors go up: the status monitor shows them and marks the outage.
        return self._call('devices') or []

    def _remembered(self, method, *args, good=bool):
        """Call the plugin; keep good answers, and while the source is down answer from them."""
        from ..plugins.base import PluginError
        key = self._key(method, *args)
        if offline():
            cached = lastgood.get(key)
            if cached:
                return _stale(cached)
        try:
            result = self._call(method, *args)
        except PluginError as exc:
            print(f'[sources] {self.name} {method} failed: {exc}')
            mark_failed(self.name, exc)
            cached = lastgood.get(key)
            return _stale(cached) if cached else None
        if good(result):
            lastgood.put(key, result)
        return result

    def device_details(self, hostname):
        result = self._remembered('device_details', hostname,
                                  good=lambda r: isinstance(r, dict) and r.get('status') not in (None, 'unknown'))
        return result or {'status': 'unknown', 'hostname': hostname,
                          'message': 'The monitoring source is not answering'}

    def resolve_ip(self, ip_address, search_device=None):
        return self._remembered('resolve_ip', ip_address, search_device)

    def port_stats(self, hostname, interface):
        return self._remembered('port_stats', hostname, interface)

    def arp(self, query):
        result = self._remembered('arp', query)
        if isinstance(result, dict):   # stale: the list is under 'value'
            return result.get('value') or []
        return result or []

    def mac_for_ip(self, ip):
        """IP to MAC from the ARP data (None if unknown)."""
        for entry in self.arp(ip):
            if entry.get('ipv4_address') == ip:
                return normalise_mac(entry.get('mac_address'))
        return None

    def ip_for_mac(self, mac):
        """MAC to its current IP from the ARP data (None if unknown)."""
        want = normalise_mac(mac)
        if not want:
            return None
        for entry in self.arp(want):
            if normalise_mac(entry.get('mac_address')) == want and entry.get('ipv4_address'):
                return entry['ipv4_address']
        return None


def monitoring():
    if _override is not None:
        return _override
    spec = registry.monitoring_source() if registry is not None else None
    return PluginMonitoring(registry, spec) if spec else NoMonitoring()


def use(monitoring=None):
    """Replace the monitoring source (an agent-fed one, or a fake in tests); ``None`` goes back to
    the plugins. Returns the previous override."""
    global _override
    previous, _override = _override, monitoring
    return previous
