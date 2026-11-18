"""German for the audit log, the event changelog and the handover (``floorbit/locales/log.de-CH.json``).

Every action the code writes to the audit log needs a German text, so a new one without fails here.
"""
import ast
import glob
import os

import pytest

from floorbit import audit, i18n, ports, timeline
from floorbit.blueprints.services import WHAT
from integrations import events

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPERS = ('_done', '_audit', '_changed')   # blueprint helpers that pass their first text on to audit.record


def _texts(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [''.join(x.value if isinstance(x, ast.Constant) else '{}' for x in node.values)]
    if isinstance(node, ast.IfExp):
        return _texts(node.body) + _texts(node.orelse)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return [a + b for a in _texts(node.left) for b in _texts(node.right)]
    return []


def _labels(func):
    """``label = '...'`` (or ``key, name, label = ..., ..., '...'``) in a function that logs ``label``."""
    logged = {a.id for c in ast.walk(func) if isinstance(c, ast.Call)
              and ast.unparse(c.func).split('.')[-1] in ('record', *HELPERS)
              for a in c.args if isinstance(a, ast.Name)}
    out = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                names = target.elts if isinstance(target, ast.Tuple) else [target]
                values = node.value.elts if isinstance(node.value, ast.Tuple) else [node.value]
                for n, v in zip(names, values, strict=False):
                    if isinstance(n, ast.Name) and n.id in logged:
                        out += _texts(v)
    return out


def actions_in_code():
    found = {v[2] for v in ports.ACTIONS.values()} | {action for _area, action in audit.ACTIONS.values()}
    found |= {f'{verb} {what}' for verb in ('Added', 'Changed', 'Removed') for what in WHAT.values()}
    found |= {f'{v[2]}: failed' for v in ports.ACTIONS.values()}
    for folder in ('floorbit', 'auth', 'integrations'):
        for path in glob.glob(os.path.join(ROOT, folder, '**', '*.py'), recursive=True):
            with open(path, encoding='utf-8') as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    found.update(_labels(node))
                if not isinstance(node, ast.Call):
                    continue
                name = ast.unparse(node.func)
                if name.split('.')[-1] == 'record' and 'audit' in path + name and len(node.args) > 1:
                    found.update(_texts(node.args[1]))
                elif name.split('.')[-1] in HELPERS and node.args:
                    found.update(t for a in node.args for t in _texts(a) if ' ' in t and t[:1].isupper())
                if name.endswith((*HELPERS, 'publish_update')):
                    found.update(t for kw in node.keywords if kw.arg == 'label' for t in _texts(kw.value))
    # '{}: failed' (ports) and 'Removed {}' (services) are spelled out above.
    return {t for t in found if t.strip('{} :') and t not in ('{}: failed', 'Removed {}')}


@pytest.mark.parametrize('action', sorted(actions_in_code()))
def test_every_audit_action_has_german(action):
    assert i18n._log_german(action.replace('{}', 'sw-01')) is not None, \
        f'{action!r} needs a German text in floorbit/locales/log.de-CH.json'


def test_found_the_actions():
    found = actions_in_code()
    assert {'Bounced port', 'Signed in', 'Muted switch alerts from Discord',
            'Ran {}: failed', 'Seat {} found on its port (swapped with {})'} <= found


def test_values_and_fields():
    opened = i18n.log_text('Incident opened: No internet at the seat', 'de-CH')
    assert opened == 'Störung eröffnet: Kein Internet am Platz'
    assert i18n.log_text('Changed cable (label, route)', 'de-CH') == 'Kabel geändert (label, route)'
    assert i18n.log_text('Incident opened: Cable cut at A-1', 'de-CH') == 'Störung eröffnet: Cable cut at A-1'
    assert i18n.log_text('Changed cable', 'en') == 'Changed cable'
    assert i18n.log_text('sw-a-01 (seat A-1)', 'de-CH') == 'sw-a-01 (seat A-1)'


def test_the_audit_log_in_german(client):
    client.post('/api/seat-blocks', json={'name': 'A', 'x': 10, 'y': 10, 'cols': 2, 'rows': 2})
    de = {'Accept-Language': 'de-CH'}
    actions = [e['action'] for e in client.get('/api/settings/audit', headers=de).get_json()['entries']]
    assert 'Sitzblock hinzugefügt' in actions
    assert 'Added seat block' in [e['action'] for e in client.get('/api/settings/audit').get_json()['entries']]
    found = client.get('/api/settings/audit?q=sitzblock', headers=de).get_json()
    assert found['total'] >= 1 and all('Sitzblock' in e['action'] for e in found['entries'])


def test_the_changelog_and_handover_in_german(client, tmp_path, monkeypatch):
    monkeypatch.setenv('TIMELINE_FILE', str(tmp_path / 'timeline.jsonl'))
    events.subscribe_once('*', timeline.on_event)
    de = {'Accept-Language': 'de-CH'}
    client.post('/api/seat-blocks', json={'name': 'A', 'x': 10, 'y': 10, 'cols': 2, 'rows': 2})
    client.post('/api/incidents', json={'seat': 'A-1', 'title': 'No internet at the seat'})
    events.publish('monitoring.offline', {'agent': True})
    titles = {e['title']: e.get('target') for e in client.get('/api/timeline', headers=de).get_json()['entries']}
    assert 'Störung eröffnet: Kein Internet am Platz' in titles
    assert titles.get('Lokaler Agent weg') == 'keine Antworten aus dem Eventnetz'
    assert client.get('/api/timeline?q=eröffnet', headers=de).get_json()['total'] >= 1
    changes = client.get('/api/handover', headers=de).get_json()['changes']
    assert any(c['action'] == 'Sitzblock hinzugefügt' for c in changes)


def test_log_alerts_and_security_kinds_inside_the_titles():
    from floorbit import log_alerts, security
    for _pid, _rx, title in log_alerts.PATTERNS:
        assert i18n.log_text(f'Log alert: {title}', 'de-CH').startswith('Log-Alarm: ') and \
            i18n.log_text(title, 'de-CH') != title
    for kind in security.KINDS:
        assert i18n._log_german(kind) is not None
    assert i18n.log_text('Security: rogue-dhcp (seat A-7)', 'de-CH') == 'Sicherheit: Fremder DHCP (Platz A-7)'


def test_traffic_anomalies_have_german():
    import re

    from floorbit.blueprints.flows import ANOMALY_KINDS
    with open(os.path.join(ROOT, 'floorbit', 'flows', 'aggregate.py'), encoding='utf-8') as f:
        tree = ast.parse(f.read())
    texts = [t for node in ast.walk(tree) if isinstance(node, ast.Call) and ast.unparse(node.func) == 'found.append'
             for elt in node.args[0].elts[2:] for t in _texts(elt)]
    assert len(texts) >= 10
    for text in [*texts, *ANOMALY_KINDS.values(), 'Anomaly']:
        sample = re.sub(r'\{\}', '7', text)
        assert i18n._log_german(sample) is not None, f'{text!r} needs a German text'
