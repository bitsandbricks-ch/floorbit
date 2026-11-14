"""What a flow is: a service name and a category, from the remote side's port or address.

Built-in rules only know well-known ports. Anything an event knows better (the LAN cache's
address, a game server range, a streaming ingest) goes in ``FLOWS_SERVICES``, a JSON list that is
checked first:

    [{"name": "LAN cache", "category": "downloads", "cidr": ["192.0.2.50/32"]},
     {"name": "Tournament servers", "category": "gaming", "cidr": ["198.51.100.0/28"]},
     {"name": "Some game", "category": "gaming", "ports": ["udp/7777-7780"]}]
"""
import ipaddress
import json

from integrations import config

CATEGORIES = ('gaming', 'streaming', 'downloads', 'updates', 'web', 'other')

# Ports the vendors publish for their games and launchers, and the plain protocols.
BUILTIN = [
    {'name': 'Steam', 'category': 'gaming', 'ports': ['udp/27015-27030', 'udp/27036', 'tcp/27036']},
    {'name': 'Battle.net', 'category': 'gaming', 'ports': ['tcp/1119', 'udp/1119']},
    {'name': 'Riot Games', 'category': 'gaming', 'ports': ['udp/5000-5500']},
    {'name': 'Minecraft', 'category': 'gaming', 'ports': ['tcp/25565']},
    {'name': 'RTMP streaming', 'category': 'streaming', 'ports': ['tcp/1935']},
    {'name': 'BitTorrent', 'category': 'downloads', 'ports': ['tcp/6881-6889', 'udp/6881-6889']},
    {'name': 'Windows Update (delivery optimisation)', 'category': 'updates', 'ports': ['tcp/7680']},
    {'name': 'Web', 'category': 'web', 'ports': ['tcp/80', 'tcp/443', 'udp/443']},
    {'name': 'DNS', 'category': 'other', 'ports': ['udp/53', 'tcp/53']},
]
PROTOS = {'tcp': 6, 'udp': 17}


class RuleError(ValueError):
    pass


def _ports(specs):
    out = []
    for spec in specs or []:
        proto, _, rng = str(spec).lower().partition('/')
        if proto not in PROTOS or not rng:
            raise RuleError(f'Port "{spec}" should look like udp/27015 or tcp/6881-6889')
        lo, _, hi = rng.partition('-')
        try:
            lo, hi = int(lo), int(hi or lo)
        except ValueError as exc:
            raise RuleError(f'Port "{spec}" should look like udp/27015 or tcp/6881-6889') from exc
        out.append((PROTOS[proto], lo, hi))
    return out


def compile_rules(rules):
    out = []
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get('name'):
            raise RuleError('Every service needs a name.')
        category = rule.get('category') or 'other'
        if category not in CATEGORIES:
            raise RuleError(f'Category "{category}" is not one of {", ".join(CATEGORIES)}.')
        try:
            nets = [ipaddress.ip_network(c, strict=False) for c in rule.get('cidr') or []]
        except ValueError as exc:
            raise RuleError(f'{rule["name"]}: {exc}') from exc
        out.append({'name': str(rule['name'])[:60], 'category': category, 'nets': nets,
                    'ports': _ports(rule.get('ports'))})
    return out


def load_rules():
    """The event's own rules first, then the built-in ones. Broken own rules are reported, not fatal."""
    raw = config.get('FLOWS_SERVICES') or ''
    own, error = [], None
    if str(raw).strip():
        try:
            own = compile_rules(json.loads(raw) if isinstance(raw, str) else raw)
        except (ValueError, RuleError) as exc:
            error = str(exc)
    return own + compile_rules(BUILTIN), error


class Classifier:
    def __init__(self, rules=None):
        self.rules = rules if rules is not None else load_rules()[0]
        self._cache = {}

    def __call__(self, remote_ip, proto, remote_port, local_port):
        key = (remote_ip, proto, remote_port, local_port)
        found = self._cache.get(key)
        if found is None:
            found = self._match(remote_ip, proto, remote_port, local_port)
            if len(self._cache) > 50_000:
                self._cache.clear()
            self._cache[key] = found
        return found

    def _match(self, remote_ip, proto, remote_port, local_port):
        try:
            addr = ipaddress.ip_address(remote_ip) if remote_ip else None
        except ValueError:
            addr = None
        for rule in self.rules:
            if rule['nets'] and addr is not None and any(addr in n for n in rule['nets']):
                return rule['name'], rule['category']
        # The service's port is usually the remote one. Only when no rule knows it, try the seat's
        # own port: a seat that serves (a game host). Two passes, so a client's random source port
        # never wins over the server's well-known one.
        for port in (remote_port, local_port):
            for rule in self.rules:
                if any(p == proto and lo <= port <= hi for p, lo, hi in rule['ports']):
                    return rule['name'], rule['category']
        return 'Other', 'other'
