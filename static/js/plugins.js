'use strict';

// Settings > Plugins: list plugins, turn them on and off, test them, read their log.
// See docs/plugins.md.
(() => {
  const list = document.getElementById('pl-list');
  const msg = document.getElementById('pl-msg');
  if (!list) return;

  async function api(method, path, body) {
    const res = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') node.className = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) node.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children) if (c != null && c !== '') node.append(c);
    return node;
  }

  function show(node, text, kind = '') {
    node.className = 'st-test-result' + (kind ? ' ' + kind : '');
    node.textContent = text;
  }

  const TRUST = { builtin: 'Ships with Floorbit', development: 'Development checkout' };

  function card(p) {
    const result = el('p', { class: 'st-test-result', role: 'status' });
    const log = el('pre', { class: 'pl-log', hidden: true });
    const toggle = el('input', { type: 'checkbox', checked: p.enabled, disabled: !!p.error,
      onchange: async () => {
        try {
          render(await api('PUT', `/api/settings/plugins/${encodeURIComponent(p.id)}`, { enabled: toggle.checked }));
          show(msg, `${p.name} is ${toggle.checked ? 'on' : 'off'}.`, 'ok');
        } catch (e) { toggle.checked = !toggle.checked; show(result, '✕ ' + e.message, 'fail'); }
      } });

    const buttons = [];
    if (p.enabled && p.has_test) {
      buttons.push(el('button', { class: 'st-btn', type: 'button', onclick: async () => {
        show(result, 'Testing…');
        try {
          const r = await api('POST', `/api/settings/plugins/${encodeURIComponent(p.id)}/test`);
          show(result, (r.ok ? '✓ ' : '✕ ') + r.message, r.ok ? 'ok' : 'fail');
        } catch (e) { show(result, '✕ ' + e.message, 'fail'); }
      } }, 'Test'));
    }
    for (const a of p.enabled ? p.actions : []) {
      buttons.push(el('button', { class: 'st-btn' + (a.danger ? ' st-btn-danger' : ''), type: 'button', title: a.help || '',
        onclick: async () => {
          if (a.danger && !window.confirm(`${a.label}: are you sure?`)) return;
          show(result, `${a.label}…`);
          try {
            const r = await api('POST', `/api/plugins/${encodeURIComponent(p.id)}/actions/${encodeURIComponent(a.id)}`, {});
            show(result, '✓ ' + r.message, 'ok');
          } catch (e) { show(result, '✕ ' + e.message, 'fail'); }
        } }, a.label));
    }
    if (p.settings_section) buttons.push(el('a', { class: 'st-btn', href: `/settings#sec-${p.settings_section}` }, 'Settings'));
    buttons.push(el('button', { class: 'st-btn', type: 'button', onclick: async () => {
      if (!log.hidden) { log.hidden = true; return; }
      try {
        const r = await api('GET', `/api/settings/plugins/${encodeURIComponent(p.id)}/log`);
        log.textContent = r.lines.map((l) => `${l.time}  ${l.line}`).join('\n');
        log.hidden = false;
      } catch (e) { show(result, '✕ ' + e.message, 'fail'); }
    } }, 'Log'));

    return el('section', { class: 'st-card', id: `pl-${p.id}` },
      el('div', { class: 'pl-head' },
        el('h2', {}, p.name),
        el('span', { class: 'pl-version' }, p.version ? `v${p.version}` : ''),
        el('span', { class: `pl-trust ${p.trust}` }, TRUST[p.trust] || p.trust),
        el('span', { class: 'pl-spacer' }),
        el('label', { class: 'pl-toggle' }, toggle, p.enabled ? 'On' : 'Off')),
      p.description ? el('p', { class: 'pl-desc' }, p.description) : '',
      p.error ? el('p', { class: 'pl-error', role: 'alert' }, '✕ ' + p.error) : '',
      el('ul', { class: 'pl-uses', 'aria-label': 'What this plugin may touch' },
        ...p.uses.map((u) => el('li', { title: u.label }, el('strong', {}, u.id), ' ', u.label))),
      el('div', { class: 'pl-actions' }, ...buttons),
      result, log);
  }

  function render(data) {
    const plugins = data.plugins || [];
    list.replaceChildren(...(plugins.length ? plugins.map(card)
      : [el('p', { class: 'st-intro' }, 'No plugins are installed.')]));
  }

  api('GET', '/api/settings/plugins').then(render).catch((e) => show(msg, '✕ ' + e.message, 'fail'));
})();
