"""LibreNMS as the monitoring source. The API calls live in client.py; this is the plugin face."""
from floorbit.builtin_plugins.librenms import client
from floorbit.plugins.base import Plugin, PluginError
from floorbit.runtime import rt


class Plugin(Plugin):
    def configured(self):
        return bool(rt.librenms_enabled)

    def devices(self):
        return client.list_devices()

    def device_details(self, hostname):
        return client.fetch_librenms_details(hostname)

    def resolve_ip(self, ip_address, search_device=None):
        return client.resolve_ip_to_switch_port(ip_address, search_device)

    def port_stats(self, hostname, interface):
        return client.fetch_librenms_device_port_stats_by_interface(hostname, interface)

    def arp(self, query):
        return client.arp_entries(query)

    def test(self):
        if not self.configured():
            raise PluginError('Set the LibreNMS URL and API token under Settings > LibreNMS first.')
        return f'Connected: LibreNMS has {len(client.list_devices())} devices.'
