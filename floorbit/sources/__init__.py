"""Where the network data comes from.

The app asks two sources for everything it knows about the network, and never calls the
NetBox or LibreNMS API modules directly:

* ``inventory()``: which switches exist (NetBox today).
* ``monitoring()``: switch status, port counters, and which switch port an IP is on
  (LibreNMS today).

Keeping every call behind these two keeps other sources possible: a local agent that
pushes data to a hosted instance, a different NMS, or fakes in tests. ``use()`` swaps
them. See docs/architecture.md.
"""
from . import librenms, netbox


class NetBoxInventory:
    name = 'netbox'

    def enabled(self):
        from ..runtime import rt
        return rt.netbox_enabled

    def fetch_devices(self):
        """[{id, name, netbox_status}] for every device with a configured role."""
        return netbox.fetch_netbox_devices()


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


_inventory = NetBoxInventory()
_monitoring = LibreNMSMonitoring()


def inventory():
    return _inventory


def monitoring():
    return _monitoring


def use(inventory=None, monitoring=None):
    """Replace a source (an agent-fed one, or a fake in tests). Returns the previous pair."""
    global _inventory, _monitoring
    previous = (_inventory, _monitoring)
    if inventory is not None:
        _inventory = inventory
    if monitoring is not None:
        _monitoring = monitoring
    return previous
