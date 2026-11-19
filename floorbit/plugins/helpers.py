"""What a plugin may import from Floorbit besides `floorbit.plugins.base` (docs/plugin-spec.md,
"Helpers"). Marketplace plugins are released apart from Floorbit, so they import these names and
nothing deeper: what lives behind them can move without breaking an installed plugin."""
import re
from urllib.parse import urlsplit

from .base import PluginError

__all__ = ['match_device', 'normalise_mac', 'parse_switches', 'summarize_port', 'uplink_pattern']

DEFAULT_UPLINK = r'uplink|trunk'


def summarize_port(port, base_url='', device_id=None):
    """A port in LibreNMS's field names (ifName, ifOperStatus, ifInOctets_rate, ...) as the
    inspector shows it: state, speeds, rates and errors."""
    from ..builtin_plugins.librenms.ports import summarize_port as summarize
    return summarize(port, base_url, device_id)


def match_device(name, devices):
    """The device for a floor-plan switch name, matched like everywhere else in Floorbit: exact
    display name, then hostname or sysName, then the short name before the first dot."""
    from integrations.monitor import StatusMonitor
    return StatusMonitor.match(name, devices)


def normalise_mac(mac):
    """aa:bb:cc:dd:ee:ff, or None for something that is not a MAC address."""
    from ..sources import normalise_mac as normalise
    return normalise(mac)


def uplink_pattern():
    """The admin's pattern for uplink and trunk ports (STATS_UPLINK_PATTERN), compiled: a seat is
    never placed on a port it matches."""
    from integrations import config
    try:
        return re.compile(config.get('STATS_UPLINK_PATTERN') or DEFAULT_UPLINK, re.IGNORECASE)
    except re.error:
        return re.compile(DEFAULT_UPLINK, re.IGNORECASE)


def parse_switches(raw):
    """A `list` setting of Name=https://address lines, as [{'name', 'url'}]; PluginError names the
    first line that isn't one."""
    out = []
    for item in raw or []:
        name, sep, url = str(item).partition('=')
        parts = urlsplit(url.strip())
        if not sep or not name.strip() or parts.scheme not in ('http', 'https') or not parts.netloc:
            raise PluginError(f'"{item}" is not Name=https://address')
        out.append({'name': name.strip(), 'url': f'{parts.scheme}://{parts.netloc}'})
    return out
