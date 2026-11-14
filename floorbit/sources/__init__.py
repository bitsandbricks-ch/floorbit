"""Where live network data comes from.

``monitoring()``: switch status, port counters, and which switch port an IP is on. The answer
comes from the monitoring plugin that is on (the built-in LibreNMS plugin,
``floorbit/builtin_plugins/librenms``), so nothing in the core talks to an NMS directly.
``use()`` swaps in another source (a local agent feeding a hosted instance, a fake in tests).
See docs/architecture.md.

Which devices exist is the inventory's job (``floorbit/inventory.py``), fed by plugins such as
NetBox (``floorbit/builtin_plugins/netbox``).
"""
import re

# Set by floorbit.plugins.init_plugins; None until the app is created.
registry = None
_override = None


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

    def devices(self):
        # Errors go up: the status monitor shows them.
        return self._call('devices') or []

    def device_details(self, hostname):
        from ..plugins.base import PluginError
        try:
            return self._call('device_details', hostname)
        except PluginError as exc:
            return {'status': 'unknown', 'message': str(exc)}

    def resolve_ip(self, ip_address, search_device=None):
        return self._quiet('resolve_ip', ip_address, search_device)

    def port_stats(self, hostname, interface):
        return self._quiet('port_stats', hostname, interface)

    def arp(self, query):
        return self._quiet('arp', query) or []

    def _quiet(self, method, *args):
        from ..plugins.base import PluginError
        try:
            return self._call(method, *args)
        except PluginError as exc:
            print(f'[sources] {self.name} {method} failed: {exc}')
            return None

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
