"""Where live network data comes from.

``monitoring()``: switch status, port counters, and which switch port an IP is on (LibreNMS
today). The app never calls the LibreNMS API module directly; ``use()`` swaps the source (a
local agent feeding a hosted instance, another NMS, a fake in tests). See docs/architecture.md.

Which devices exist is the inventory's job (``floorbit/inventory.py``), fed by plugins such as
NetBox (``floorbit/builtin_plugins/netbox``).
"""
from . import librenms


class LibreNMSMonitoring:
    name = 'librenms'

    def enabled(self):
        from ..runtime import rt
        return rt.librenms_enabled

    def device_details(self, hostname):
        """Status, IP, CPU, memory, temperature, port summary and traffic of one switch."""
        return librenms.fetch_librenms_details(hostname)

    def resolve_ip(self, ip_address, search_device=None):
        """The switch and port an IP is plugged into, with that port's stats, or None."""
        return librenms.resolve_ip_to_switch_port(ip_address, search_device)

    def port_stats(self, hostname, interface):
        """One port's state, speed, traffic and errors."""
        return librenms.fetch_librenms_device_port_stats_by_interface(hostname, interface)


_monitoring = LibreNMSMonitoring()


def monitoring():
    return _monitoring


def use(monitoring=None):
    """Replace the monitoring source (an agent-fed one, or a fake in tests). Returns the previous one."""
    global _monitoring
    previous = _monitoring
    if monitoring is not None:
        _monitoring = monitoring
    return previous
