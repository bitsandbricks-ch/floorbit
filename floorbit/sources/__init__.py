"""Where live network data comes from.

``monitoring()``: switch status, port counters, and which switch port an IP is on. The answer
comes from the monitoring plugin that is on (the built-in LibreNMS plugin,
``floorbit/builtin_plugins/librenms``), so nothing in the core talks to an NMS directly.
``use()`` swaps in another source (a fake in tests). With a local agent enrolled, a hosted
instance asks the agent instead (floorbit/agent_link.py).
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
_health = {'source': None, 'label': None, 'ok': True, 'offline_since': None, 'last_ok': None, 'error': None}


# Set when the source may answer again (an agent connected): the status monitor polls at once.
status_wake = threading.Event()


def wake_status_monitor():
    status_wake.set()


def health():
    with _health_lock:
        return dict(_health)


def mark_ok(source, label=None):
    """Returns how long the source was down (seconds), or None if it wasn't."""
    with _health_lock:
        was_down = _health['offline_since']
        _health.update(source=source, label=label or source, ok=True, offline_since=None, last_ok=time.time(),
                       error=None)
    return time.time() - was_down if was_down else None


def mark_failed(source, error, label=None):
    """Returns True when this is the start of an outage."""
    with _health_lock:
        starting = _health['offline_since'] is None
        _health.update(source=source, label=label or source, ok=False, error=str(error)[:300],
                       offline_since=_health['offline_since'] or time.time())
    return starting


def mark_off():
    """No monitoring source at all: an outage marked while one was still asked is over."""
    with _health_lock:
        if _health['offline_since'] is not None:
            _health.update(source=None, label=None, ok=True, offline_since=None, error=None)


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

    def device_ports(self, hostname):
        return []

    def port_clients(self, hostname):
        return []

    def neighbours(self, hostname):
        return []

    def device_facts(self, hostname):
        return {}

    def arp(self, query):
        return []

    def mac_for_ip(self, ip):
        from ..dhcp_leases import leases
        return leases.mac_for_ip(ip)

    def ip_for_mac(self, mac):
        from ..dhcp_leases import leases
        return leases.ip_for_mac(mac)


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
            mark_failed(self.name, exc, self.label)
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
        found = self._remembered('resolve_ip', ip_address, search_device)
        if isinstance(found, dict) and found.get('port'):
            return {**found, 'answered_by': found.get('answered_by') or self.name}
        # Not known here (or only the MAC): the other monitoring source may know it (issue #945).
        other = self._ask_others('resolve_ip', ip_address, search_device,
                                 good=lambda r: isinstance(r, dict) and r.get('port'))
        return other or found

    def _ask_others(self, method, *args, good=bool):
        """The first good answer from the other monitoring plugins that are on and set up, marked
        with the one that gave it. None when none knows."""
        from ..plugins.base import PluginError
        registry = getattr(self, '_registry', None)
        if registry is None or not hasattr(registry, 'monitoring_sources'):
            return None
        for spec in registry.monitoring_sources():
            if spec.id in (self.name, 'demo'):
                continue
            try:
                if not registry.call(spec, 'configured'):
                    continue
                result = registry.call(spec, method, *args)
            except PluginError:
                continue
            if good(result):
                return {**result, 'answered_by': spec.id} if isinstance(result, dict) else result
        return None

    def port_stats(self, hostname, interface):
        return self._remembered('port_stats', hostname, interface)

    def device_ports(self, hostname):
        """Every port of a switch, live (the needs-attention watch). Optional for plugins."""
        from ..plugins.base import PluginError
        if offline() or not hasattr(self._spec.plugin_class() or object, 'device_ports'):
            return []
        try:
            return self._call('device_ports', hostname) or []
        except PluginError as exc:
            print(f'[sources] {self.name} device_ports failed: {exc}')
            return []

    def port_clients(self, hostname):
        """[{port, mac, vlan}] from a switch's MAC table (floorbit/port_clients.py). Optional for
        plugins; errors go up, so the page names the switch that didn't answer."""
        from ..plugins.base import PluginError
        if not hasattr(self._spec.plugin_class() or object, 'port_clients'):
            raise PluginError(f'{self.label} has no MAC tables')
        return self._call('port_clients', hostname) or []

    def neighbours(self, hostname):
        """[{port, remote, remote_port, protocol}] from LLDP or CDP (floorbit/links.py). Optional for
        plugins: one without it has nothing to suggest."""
        if offline() or not hasattr(self._spec.plugin_class() or object, 'neighbours'):
            return []
        return self._call('neighbours', hostname) or []

    def device_facts(self, hostname):
        """What a device is (VLANs, networks, optics, ...), shaped like telemetry's Device.summary(),
        for discovery. Every monitoring plugin that is on and knows facts answers; telemetry's facts
        come first and the others fill what it doesn't say (issue #966). Optional for plugins."""
        from ..plugins.base import PluginError
        # Demo data replaces the live sources; otherwise every set-up one may know something.
        others = [] if self.name == 'demo' else [
            s for s in self._registry.monitoring_sources() if s.id not in ('demo', self.name)]
        out = {}
        for spec in sorted([self._spec, *others], key=lambda s: s.id != 'telemetry'):
            if not hasattr(spec.plugin_class() or object, 'device_facts'):
                continue
            try:
                if spec is not self._spec and not self._registry.call(spec, 'configured'):
                    continue
                facts = self._registry.call(spec, 'device_facts', hostname)
            except PluginError as exc:
                print(f'[sources] {spec.id} device_facts failed: {exc}')
                continue
            for key, value in (facts if isinstance(facts, dict) else {}).items():
                if value not in (None, '', [], {}) and key not in out:
                    out[key] = value
        return out

    def arp(self, query):
        result = self._remembered('arp', query)
        if isinstance(result, dict):   # stale: the list is under 'value'
            return result.get('value') or []
        return result or self._ask_others('arp', query) or []

    def mac_for_ip(self, ip):
        """IP to MAC: the DHCP server's lease if its syslog told us (fresh), else the ARP data
        (None if unknown)."""
        leased = super().mac_for_ip(ip)
        if leased:
            return leased
        for entry in self.arp(ip):
            if entry.get('ipv4_address') == ip:
                return normalise_mac(entry.get('mac_address'))
        return None

    def ip_for_mac(self, mac):
        """MAC to its current IP: the DHCP lease, else the ARP data (None if unknown)."""
        want = normalise_mac(mac)
        if not want:
            return None
        leased = super().ip_for_mac(want)
        if leased:
            return leased
        for entry in self.arp(want):
            if normalise_mac(entry.get('mac_address')) == want and entry.get('ipv4_address'):
                return entry['ipv4_address']
        return None


_agent = None


def call_monitoring(registry, method, *args):
    """Run one monitoring call the way ``monitoring()`` would, for the local agent's executor
    (floorbit-agent): the chosen plugin first, and for an IP or MAC it doesn't know, the other
    monitoring plugins (issue #945)."""
    from ..plugins.base import PluginError
    spec = registry.monitoring_source() if registry is not None else None
    if spec is None:
        raise PluginError('No monitoring plugin is set up on the agent (LIBRENMS_URL and LIBRENMS_TOKEN?)')
    source = PluginMonitoring(registry, spec)
    if method == 'resolve_ip':
        return source.resolve_ip(*args)
    if method == 'arp':
        result = registry.call(spec, 'arp', *args)
        return result or source._ask_others('arp', *args) or []
    if method == 'device_facts':
        return source.device_facts(*args)
    return registry.call(spec, method, *args)


def monitoring():
    global _agent
    if _override is not None:
        return _override
    # A hosted instance: the event's own LibreNMS is reached through the local agent (issue #2).
    from .. import agent_link
    if agent_link.active():
        if not agent_link.monitoring_set_up():
            # The agent answered that it has nothing to monitor with: asking it anyway made every
            # page's call fail and read as an agent outage. Demo data, when on, still shows the hall.
            mark_off()
            demo = registry is not None and registry.demo_on()
            return PluginMonitoring(registry, registry.specs['demo']) if demo else NoMonitoring()
        if _agent is None:
            _agent = agent_link.monitoring_source()
        return _agent
    spec = registry.monitoring_source() if registry is not None else None
    return PluginMonitoring(registry, spec) if spec else NoMonitoring()


def use(monitoring=None):
    """Replace the monitoring source (an agent-fed one, or a fake in tests); ``None`` goes back to
    the plugins. Returns the previous override."""
    global _override
    previous, _override = _override, monitoring
    return previous
