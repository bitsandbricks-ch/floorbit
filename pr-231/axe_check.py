import json, collections
from playwright.sync_api import sync_playwright
B = 'http://localhost:5073'
AXE = open('/home/user/floorbit/frontend/node_modules/axe-core/axe.min.js').read()
pages = ['/plan', '/incidents', '/problems', '/handover', '/health', '/power', '/stats', '/traffic', '/logs', '/cables', '/gear', '/runbooks', '/teams', '/schedule', '/network-status', '/dashboard', '/wifi', '/timeline', '/report', '/jobs', '/security', '/dns', '/inventory']
seen = collections.Counter()
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
    for scheme in ('light', 'dark'):
        pg = b.new_page(viewport={'width': 1440, 'height': 900}, color_scheme=scheme)
        pg.goto(f'{B}/login'); pg.fill('input[name=username]', 'demo'); pg.fill('input[name=password]', 'demo-screenshots')
        pg.click('button[type=submit]'); pg.wait_for_load_state('load'); pg.wait_for_timeout(800)
        for path in pages:
            pg.goto(B + path, wait_until='domcontentloaded'); pg.wait_for_timeout(2000)
            pg.add_script_tag(content=AXE)
            r = pg.evaluate("axe.run(document, {runOnly: ['wcag2a','wcag2aa']}).then(r => r.violations.flatMap(v => v.nodes.map(n => ({id: v.id, d: (n.any[0]||{}).data, cls: (n.html.match(/class=\"([^\"]*)\"/)||[])[1], parent: n.target.join(' ').slice(-90)}))))")
            for n in r:
                d = n['d'] or {}
                key = (scheme, d.get('fgColor'), d.get('bgColor'), d.get('contrastRatio'), d.get('fontSize'))
                if not seen[key]: print(path, n['id'], key, n['parent'])
                seen[key] += 1
        pg.close()
    b.close()
