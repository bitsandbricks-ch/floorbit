"""Write docs/api-reference.md from the app's routes, so the reference can't drift (issue #53).

    python scripts/api_reference.py          # rewrite the file
    python scripts/api_reference.py --check  # exit 1 when it is out of date (CI and the tests)

For every ``/api/`` route: its methods, the permission it needs (auth/roles.py RULES), the feature
it belongs to (floorbit/features.py) and the module that serves it. What each endpoint takes and
answers is in that module's docstring and the area's own doc.
"""
import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'docs', 'api-reference.md')
REPO = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/'
SAFE = {'GET'}
OPEN_ENDPOINTS = ('auth.login', 'auth.logout', 'auth.me', 'auth.start', 'auth.callback')   # Auth.is_public


def _summary(module):
    doc = inspect.getdoc(sys.modules[module]) or ''
    return doc.split('\n\n', 1)[0].replace('\n', ' ').strip()


def render(app):
    from auth import DEFAULT_PUBLIC_PATHS, roles
    from floorbit import features
    public_paths = tuple(DEFAULT_PUBLIC_PATHS.split(','))   # the defaults, not this machine's AUTH_PUBLIC_PATHS
    areas = {}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith('/api/'):
            continue
        view = app.view_functions[rule.endpoint]
        module = view.__module__
        path = rule.rule
        # The guard sees a real path; a placeholder stands in for the variable part.
        probe = path.replace('<', '').replace('>', '').replace('path:', '')
        methods = sorted(rule.methods - {'HEAD', 'OPTIONS'}, key=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].index)
        open_to_all = rule.endpoint in OPEN_ENDPOINTS or getattr(view, '_auth_public', False) or \
            any(probe == p or probe.startswith(p + '/') for p in public_paths)
        for method in methods:
            if open_to_all:
                needs = 'anyone'
            else:
                needs = roles.needed_for(probe.rstrip('/'), method)
                if needs == 'floorplan.view' and method in SAFE:
                    needs = 'floorplan.view (open while `AUTH_PUBLIC_READ` is on)'
                else:
                    needs = f'`{needs}`'
            feature = features.owner(probe)
            areas.setdefault(module, []).append((path, method, needs, f'`{feature}`' if feature else ''))

    lines = [
        '# API reference',
        '',
        '<!-- Written by scripts/api_reference.py from the app\'s routes. Don\'t edit by hand: run the script. -->',
        '',
        'Every `/api/` endpoint, the permission it needs and the feature it belongs to. How to sign in with a',
        'token, the version promise and webhooks are in [api.md](api.md). What an endpoint takes and answers is',
        'at the top of the module that serves it. A request a role can\'t make answers 403; an endpoint whose',
        'feature is turned off answers 404 ([features.md](features.md)).',
        '',
    ]
    for module in sorted(areas, key=lambda m: (m.startswith('floorbit.builtin_plugins'), m)):
        source = module.replace('.', '/') + '.py'
        if not os.path.exists(os.path.join(ROOT, source)):
            source = module.replace('.', '/') + '/__init__.py'
        lines += [f'## {module}', '']
        summary = _summary(module)
        if summary:
            lines += [summary, '']
        lines += [f'Source: [`{source}`]({REPO}{source})', '', '| Method | Path | Needs | Feature |',
                  '| --- | --- | --- | --- |']
        for path, method, needs, feature in sorted(areas[module]):
            lines.append(f'| {method} | `{path}` | {needs} | {feature} |')
        lines.append('')
    return '\n'.join(lines)


def main():
    sys.path.insert(0, ROOT)
    os.environ.setdefault('SECRET_KEY', 'api-reference')
    from floorbit import create_app
    text = render(create_app(start_background=False))
    if '--check' in sys.argv:
        with open(OUT, encoding='utf-8') as f:
            if f.read() != text:
                print('docs/api-reference.md is out of date: run python scripts/api_reference.py')
                return 1
        return 0
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
