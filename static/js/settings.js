'use strict';

// Settings page: renders the schema from GET /api/settings and saves only the
// fields the user changed. A value of null in the PUT body resets that field to
// its environment variable or built-in default.

(() => {
  const sectionsEl = document.getElementById('st-sections');
  const statusGrid = document.getElementById('st-status-grid');
  const form       = document.getElementById('st-form');
  const saveBtn    = document.getElementById('st-save');
  const discardBtn = document.getElementById('st-discard');
  const saveMsg    = document.getElementById('st-save-msg');

  const TESTABLE = { netbox: 'NetBox', librenms: 'LibreNMS' };
  const SOURCE_LABEL = { saved: 'Saved', env: 'From env', default: 'Default' };

  let state = null;          // last payload from the server
  const changes = {};        // key -> new value, or null for "reset"

  // ── helpers ─────────────────────────────────────────────────────────────────────────
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) if (c != null) node.append(c);
    return node;
  }

  async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-JSON error page */ }
    if (!res.ok) throw new Error((data && data.error) || `${method} ${path} failed (${res.status})`);
    return data;
  }

  function isDirty() { return Object.keys(changes).length > 0; }

  function setMessage(text, kind = '') {
    saveMsg.textContent = text;
    saveMsg.className = 'st-savebar-msg' + (kind ? ' ' + kind : '');
  }

  function refreshSaveBar() {
    const n = Object.keys(changes).length;
    saveBtn.disabled = n === 0;
    discardBtn.disabled = n === 0;
    if (n) setMessage(`${n} unsaved change${n === 1 ? '' : 's'}`);
  }

  function sameValue(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  // ── rendering ──────────────────────────────────────────────────────────────────────
  function renderStatus() {
    const s = state.status;
    const redis = s.redis || {};
    const items = [
      ['NetBox',   s.netbox_enabled,   s.netbox_enabled ? 'Configured' : 'Not configured, manual switches only'],
      ['LibreNMS', s.librenms_enabled, s.librenms_enabled ? 'Configured' : 'Not configured, no live status'],
      ['Redis',    redis.connected,    redis.connected ? `${redis.host}:${redis.port}` : `Not connected (${redis.host || '?'}:${redis.port || '?'})`],
    ];
    statusGrid.replaceChildren(...items.map(([name, on, sub]) =>
      el('div', { class: 'st-status-item' },
        el('span', { class: 'st-dot ' + (on ? 'on' : 'off') }),
        el('div', {}, el('strong', { text: name }), el('small', { text: sub })))));

    const redisTest = el('div', { class: 'st-input-row', style: 'margin-top:10px' });
    const redisResult = el('div', { class: 'st-test-result' });
    redisTest.append(el('button', {
      type: 'button', class: 'st-btn', text: 'Test Redis',
      onclick: () => runTest('redis', redisResult),
    }));
    statusGrid.append(el('div', { style: 'grid-column:1/-1' }, redisTest, redisResult,
      el('p', { class: 'st-help', text: 'Redis is configured with the REDIS_* environment variables.' })));
  }

  function fieldValue(field) {
    if (field.key in changes) {
      const v = changes[field.key];
      if (v === null) return null;  // pending reset; shown as current effective value
      return v;
    }
    return state.values[field.key].value;
  }

  function renderField(field) {
    const info = state.values[field.key];
    const id = 'f-' + field.key.replace(/\./g, '-');
    const pendingReset = changes[field.key] === null;
    const dirty = field.key in changes;

    const meta = el('div', { class: 'st-meta' });
    const badge = dirty
      ? el('span', { class: 'st-badge dirty', text: pendingReset ? 'Will reset' : 'Unsaved' })
      : el('span', { class: 'st-badge ' + info.source, text: SOURCE_LABEL[info.source] });
    meta.append(badge);
    if (field.env) meta.append(el('span', { text: field.env + (info.env_set ? ' is set' : '') }));
    if (info.source === 'saved' && !dirty) {
      meta.append(el('button', {
        type: 'button', class: 'st-link',
        text: field.type === 'secret' ? 'Remove saved token' : 'Reset',
        onclick: () => { changes[field.key] = null; rerender(); },
      }));
    }
    if (dirty) {
      meta.append(el('button', {
        type: 'button', class: 'st-link', text: 'Undo',
        onclick: () => { delete changes[field.key]; rerender(); },
      }));
    }

    let input;
    const row = el('div', { class: 'st-input-row' });
    const onChange = (val) => {
      const original = field.type === 'secret' ? '' : info.value;
      if (sameValue(val, original)) delete changes[field.key];
      else changes[field.key] = val;
      // Update badge without re-rendering (keeps focus).
      const fresh = renderField(field);
      wrapper.querySelector('.st-meta').replaceWith(fresh.querySelector('.st-meta'));
      refreshSaveBar();
    };

    if (field.type === 'bool') {
      const current = pendingReset ? info.value : fieldValue(field);
      input = el('input', { type: 'checkbox', id, checked: !!current });
      input.addEventListener('change', () => onChange(input.checked));
      row.append(el('label', { class: 'st-switch' }, input, el('span')));
    } else if (field.type === 'secret') {
      const pending = typeof changes[field.key] === 'string' ? changes[field.key] : '';
      input = el('input', {
        type: 'password', id, value: pending, autocomplete: 'new-password',
        placeholder: info.is_set ? '•••••••• (set, type to replace)' : 'Not set',
      });
      input.addEventListener('input', () => onChange(input.value));
      row.append(input);
    } else if (field.type === 'int') {
      const current = pendingReset ? info.value : fieldValue(field);
      input = el('input', { type: 'number', id, value: current, min: field.min, max: field.max, step: 1 });
      input.addEventListener('input', () => {
        const n = Number(input.value);
        const bad = input.value === '' || !Number.isInteger(n) ||
          (field.min != null && n < field.min) || (field.max != null && n > field.max);
        input.classList.toggle('invalid', bad);
        onChange(bad ? input.value : n);
      });
      row.append(input);
      if (field.unit) row.append(el('span', { class: 'st-unit', text: field.unit }));
    } else if (field.type === 'choice') {
      const current = pendingReset ? info.value : fieldValue(field);
      input = el('select', { id },
        field.options.map(o => el('option', { value: o.value, text: o.label, selected: o.value === current })));
      input.addEventListener('change', () => { onChange(input.value); updateThemeHints(); });
      row.append(input);
    } else if (field.type === 'color') {
      // A text field (empty means "derive it") with a colour picker beside it.
      const current = (pendingReset ? info.value : fieldValue(field)) || '';
      // An empty field shows a dimmed grey picker: the colour is derived, not picked.
      const picker = el('input', { type: 'color', value: current || '#808080', class: current ? '' : 'st-derived',
                                   'aria-label': field.label + ' picker' });
      input = el('input', { type: 'text', id, value: current, placeholder: 'Derived', spellcheck: 'false', maxlength: 7 });
      const sync = (v) => {
        const ok = v === '' || /^#[0-9a-f]{6}$/i.test(v);
        input.classList.toggle('invalid', !ok);
        if (ok && v) picker.value = v;
        picker.classList.toggle('st-derived', !v);
        onChange(v.toLowerCase());
        updateThemeHints();
      };
      picker.addEventListener('input', () => { input.value = picker.value; sync(picker.value); });
      input.addEventListener('input', () => sync(input.value.trim()));
      row.append(picker, input);
    } else if (field.type === 'image') {
      const current = (pendingReset ? info.value : fieldValue(field)) || '';
      const preview = el('img', { class: 'st-logo-preview' + (current ? '' : ' hidden'), src: current || undefined, alt: '' });
      input = el('input', { type: 'file', id, accept: 'image/svg+xml,image/png,image/jpeg,image/webp' });
      const remove = el('button', { type: 'button', class: 'st-btn' + (current ? '' : ' hidden'), text: 'Remove' });
      input.addEventListener('change', () => {
        const file = input.files[0];
        if (!file) return;
        if (file.size > 256 * 1024) { setMessage(`${field.label} must be 256 KB or smaller`, 'error'); input.value = ''; return; }
        const reader = new FileReader();
        reader.onload = () => {
          preview.src = reader.result;
          preview.classList.remove('hidden');
          remove.classList.remove('hidden');
          onChange(reader.result);
        };
        reader.readAsDataURL(file);
      });
      remove.addEventListener('click', () => {
        preview.classList.add('hidden');
        remove.classList.add('hidden');
        input.value = '';
        onChange('');
      });
      row.append(preview, input, remove);
    } else if (field.type === 'list') {
      const current = pendingReset ? info.value : fieldValue(field);
      input = el('input', { type: 'text', id, value: (current || []).join(', ') });
      input.addEventListener('input', () =>
        onChange(input.value.split(',').map(s => s.trim()).filter(Boolean)));
      row.append(input);
    } else {
      const current = pendingReset ? info.value : fieldValue(field);
      input = el('input', {
        type: field.type === 'url' ? 'url' : 'text', id, value: current || '',
        placeholder: field.placeholder, spellcheck: 'false',
      });
      input.addEventListener('input', () => {
        const v = input.value.trim();
        input.classList.toggle('invalid', field.type === 'url' && v !== '' && !/^https?:\/\//i.test(v));
        onChange(v.replace(/\/+$/, ''));
      });
      row.append(input);
    }
    if (pendingReset) input.disabled = true;

    const control = el('div', { class: 'st-control' }, row);
    if (field.help) control.append(el('div', { class: 'st-help', text: field.help }));
    control.append(meta);

    const wrapper = el('div', { class: 'st-field', 'data-key': field.key, 'data-theme-only': field.theme },
      el('label', { for: id, text: field.label }), control);
    return wrapper;
  }

  function renderSection(section) {
    const fields = state.fields.filter(f => f.section === section.id);
    const head = el('div', { class: 'st-card-head' },
      el('div', {}, el('h2', { text: section.title }),
        el('p', { class: 'st-card-desc', text: section.description })));
    const card = el('section', { class: 'st-card', id: 'sec-' + section.id }, head);

    let result = null;
    if (TESTABLE[section.id]) {
      result = el('div', { class: 'st-test-result' });
      head.append(el('button', {
        type: 'button', class: 'st-btn', text: 'Test connection',
        onclick: () => runTest(section.id, result),
      }));
    }
    card.append(...fields.map(renderField));
    if (result) card.append(result);
    if (section.id === 'appearance') card.append(el('div', { class: 'st-test-result', id: 'st-theme-hint' }));
    return card;
  }

  // ── appearance hints ─────────────────────────────────────────────────────────────────
  // Same maths as floorbit/theme.py: warn when the accent is hard to see on the background.
  function luminance(hex) {
    const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map(v => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  function contrast(a, b) {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  }
  function currentValue(key) {
    if (key in changes) return changes[key] === null ? state.values[key].value : changes[key];
    return state.values[key].value;
  }
  function updateThemeHints() {
    const custom = currentValue('theme.preset') === 'custom';
    document.querySelectorAll('[data-theme-only="custom"]').forEach(f => f.classList.toggle('st-muted', !custom));
    const hint = document.getElementById('st-theme-hint');
    if (!hint) return;
    const hex = /^#[0-9a-f]{6}$/i;
    const accent = currentValue('theme.accent');
    const bg = currentValue('theme.background') || '#0b0b0f';
    if (!custom) {
      hint.className = 'st-test-result';
      hint.textContent = 'The colours below apply when Theme is Custom.';
    } else if (hex.test(accent) && hex.test(bg)) {
      const ratio = contrast(accent, bg);
      const ok = ratio >= 3;
      hint.className = 'st-test-result ' + (ok ? 'ok' : 'fail');
      hint.textContent = (ok ? '✓ ' : '! ') + `Accent on background: ${ratio.toFixed(1)}:1` +
        (ok ? '' : '. Below 3:1, buttons and focus rings will be hard to see.');
    } else {
      hint.className = 'st-test-result';
      hint.textContent = '';
    }
  }

  function rerender() {
    sectionsEl.replaceChildren(...state.sections.map(renderSection));
    updateThemeHints();
    refreshSaveBar();
  }

  function render() {
    renderStatus();
    rerender();
  }

  // ── actions ─────────────────────────────────────────────────────────────────────────
  async function runTest(service, resultEl) {
    resultEl.className = 'st-test-result';
    resultEl.textContent = 'Testing…';
    // Send unsaved form values so a URL/token can be checked before saving.
    const body = {};
    for (const [k, v] of Object.entries(changes)) {
      if (k.startsWith(service + '.') && v !== null) body[k] = v;
    }
    try {
      const r = await api('POST', `/api/settings/test/${service}`, body);
      resultEl.className = 'st-test-result ' + (r.ok ? 'ok' : 'fail');
      resultEl.textContent = (r.ok ? '✓ ' : '✕ ') + r.message;
    } catch (e) {
      resultEl.className = 'st-test-result fail';
      resultEl.textContent = '✕ ' + e.message;
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!isDirty()) return;
    saveBtn.disabled = true;
    setMessage('Saving…');
    try {
      const savedKeys = Object.keys(changes);
      state = await api('PUT', '/api/settings', { ...changes });
      for (const k of Object.keys(changes)) delete changes[k];
      render();
      const themeChanged = savedKeys.some(k => k.startsWith('theme.'));
      setMessage(themeChanged ? 'Saved. Reloading to show the new theme…' : 'Saved. Changes apply immediately.', 'ok');
      // The theme is rendered into the page by the server, so show it by reloading.
      if (themeChanged) setTimeout(() => location.reload(), 600);
    } catch (err) {
      setMessage(err.message, 'error');
      saveBtn.disabled = false;
    }
  });

  discardBtn.addEventListener('click', () => {
    for (const k of Object.keys(changes)) delete changes[k];
    rerender();
    setMessage('');
  });

  window.addEventListener('beforeunload', (e) => {
    if (isDirty()) { e.preventDefault(); e.returnValue = ''; }
  });

  // ── init ────────────────────────────────────────────────────────────────────────────
  api('GET', '/api/settings')
    .then(data => { state = data; render(); })
    .catch(err => {
      sectionsEl.replaceChildren(el('div', { class: 'st-card' },
        el('h2', { text: 'Could not load settings' }),
        el('p', { class: 'st-card-desc', text: err.message })));
    });
})();
