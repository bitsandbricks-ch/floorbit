"""What a flow is: a service name and a category, from the remote side's port or address, or the
site the seat looked up before it connected (names.py, #1600).

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

from ..traffic_categories import BUILTIN, BUILTIN_IDS, ID_RE

# The built-in categories; a tenant adds its own (floorbit/traffic_categories.py, #1622), which reach
# the classifier with the applications' rules. One colour per kind on every chart (#1408).
CATEGORIES = BUILTIN_IDS
CATEGORY_COLOURS = {c['id']: c['colour'] for c in BUILTIN}

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


def compile_rules(rules, own_categories=False):
    """``own_categories``: rules from Floorbit's applications, which may name the tenant's own
    categories (checked when they were saved); ``FLOWS_SERVICES`` keeps to the built-in ones."""
    out = []
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get('name'):
            raise RuleError('Every service needs a name.')
        category = rule.get('category') or 'other'
        if category not in CATEGORIES and not (own_categories and ID_RE.match(str(category))):
            raise RuleError(f'Category "{category}" is not one of {", ".join(CATEGORIES)}.')
        try:
            nets = [ipaddress.ip_network(c, strict=False) for c in rule.get('cidr') or []]
        except ValueError as exc:
            raise RuleError(f'{rule["name"]}: {exc}') from exc
        sites = rule.get('sites') or []
        out.append({'name': str(rule['name'])[:60], 'category': category, 'nets': nets,
                    'ports': _ports(rule.get('ports')),
                    'sites': {str(s).lower() for s in sites} if isinstance(sites, list) else set()})
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
    return own + _builtin_rules(), error


def _builtin_rules():
    return [{**rule, 'builtin': True} for rule in compile_rules(BUILTIN)]


class Classifier:
    def __init__(self, rules=None):
        self.rules = rules if rules is not None else load_rules()[0]
        self._base = self.rules
        self._cache = {}

    def set_applications(self, rules):
        """The rules Floorbit's applications and game servers make (floorbit/applications.py), checked
        before the built-in ones. Broken ones are skipped: they were checked when they were saved."""
        extra = []
        for rule in rules or []:
            try:
                extra += compile_rules([rule], own_categories=True)
            except RuleError:
                continue
        builtin = _builtin_rules()
        own = self._base[:max(0, len(self._base) - len(builtin))]
        self.rules = own + extra + self._base[len(own):]
        self._cache = {}

    def __call__(self, remote_ip, proto, remote_port, local_port, site=None):
        """``site``: what the seat looked up before this flow, when DNS told the agent (names.py)."""
        key = (remote_ip, proto, remote_port, local_port, site)
        found = self._cache.get(key)
        if found is None:
            found = self._match(remote_ip, proto, remote_port, local_port, site)
            if len(self._cache) > 50_000:
                self._cache.clear()
            self._cache[key] = found
        return found

    def _match(self, remote_ip, proto, remote_port, local_port, site=None):
        try:
            addr = ipaddress.ip_address(remote_ip) if remote_ip else None
        except ValueError:
            addr = None
        for rule in self.rules:
            if rule['nets'] and addr is not None and any(addr in n for n in rule['nets']):
                return rule['name'], rule['category']
        if site:
            # An event's or an application's own port still wins (a game's servers over the
            # launcher's site), but the site beats the built-in ports: they only say "Web".
            for rule in self.rules:
                if rule.get('builtin'):
                    continue
                if any(p == proto and lo <= remote_port <= hi for p, lo, hi in rule['ports']):
                    return rule['name'], rule['category']
            for rule in self.rules:
                if site in rule['sites']:
                    return rule['name'], rule['category']
        # The service's port is usually the remote one. Only when no rule knows it, try the seat's
        # own port: a seat that serves (a game host). Two passes, so a client's random source port
        # never wins over the server's well-known one.
        for port in (remote_port, local_port):
            for rule in self.rules:
                if any(p == proto and lo <= port <= hi for p, lo, hi in rule['ports']):
                    return rule['name'], rule['category']
        return 'Other', 'other'
