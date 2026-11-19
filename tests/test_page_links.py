"""Links the server hands to pages (a problem's "Open", a service's tile) go to a page the app has.
Pages moved into tabs and widgets left /health, /stats and /dashboard behind, and nothing caught it."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"""['"]link['"]\s*:\s*f?['"](/[^'"{?#]*)""")


def _routes():
    app = (ROOT / 'frontend/src/App.tsx').read_text()
    out = []
    for path in re.findall(r'<Route path="([^"]+)"', app):
        if path == '*':
            continue
        pattern = re.sub(r'/:[^/]+\?', '(/[^/]+)?', path)
        pattern = re.sub(r':[^/]+', '[^/]+', pattern)
        out.append(re.compile(pattern + '$'))
    return out


def test_every_link_from_the_server_opens_a_page():
    routes = _routes()
    assert routes, 'no routes found in App.tsx'
    dead = []
    for folder in ('floorbit', 'integrations'):
        for file in (ROOT / folder).rglob('*.py'):
            for path in LINK.findall(file.read_text()):
                if path.startswith('/api/') or path == '/':
                    continue
                if not any(r.match(path.rstrip('/') or '/') for r in routes):
                    dead.append(f'{file.relative_to(ROOT)}: {path}')
    assert not dead, 'links to pages the app does not have:\n' + '\n'.join(dead)
