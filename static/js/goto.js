// "Go to" (Ctrl+K / ⌘K) on the floor plan and Settings, like the React pages' palette (issue #250).
// The page list comes from GET /api/pages, so all pages offer the same pages to the same account.
// The button goes into each [data-goto] element; recent pages share the React app's storage key.
'use strict';

(function () {
  const RECENT_KEY = 'floorbit-recent-pages';
  const RECENT_MAX = 5;
  const RECENT_KEPT = 10;
  const mac = /Mac|iPhone|iPad/.test(navigator.platform);
  let pages = null;
  let dialog = null;

  function recent() {
    try {
      const v = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
      return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : [];
    } catch (_) { return []; }
  }
  function remember(path) {
    try {
      localStorage.setItem(RECENT_KEY, JSON.stringify([path, ...recent().filter((p) => p !== path)].slice(0, RECENT_KEPT)));
    } catch (_) { /* private mode: no history */ }
  }
  const fold = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  function load() {
    if (!pages) {
      pages = fetch('/api/pages', { credentials: 'same-origin' })
        .then((r) => (r.ok ? r.json() : { pages: [] }))
        .then((b) => b.pages || [])
        .catch(() => { pages = null; return []; });
    }
    return pages;
  }

  // The page's own buttons, typed instead of clicked (issue #254).
  function actions() {
    const out = [];
    if (window.floorTheme && !document.documentElement.dataset.themeLock) {
      const dark = window.floorTheme.current() === 'light';
      out.push({ href: '#theme', label: dark ? 'Switch to dark theme' : 'Switch to light theme', run: () => window.floorTheme.toggle() });
    }
    const shortcuts = document.getElementById('shortcuts-backdrop');
    if (shortcuts) out.push({ href: '#shortcuts', label: 'Keyboard shortcuts', run: () => shortcuts.classList.remove('hidden') });
    // Sign-in on and signed in: the sidebar's data says so (templates/_nav.html).
    let boot = {};
    try { boot = JSON.parse((document.getElementById('fb-nav-data') || {}).textContent || '{}'); } catch (_) { /* no sidebar */ }
    if (document.querySelector('form.user-menu') || (boot.signOut && boot.user)) {
      out.push({ href: '#sign-out', label: 'Sign out', run: () => {
        const form = document.createElement('form');
        form.method = 'post';
        form.action = '/logout';
        document.body.append(form);
        form.submit();
      } });
    }
    return out;
  }

  function build() {
    dialog = document.createElement('dialog');
    dialog.className = 'goto-dialog';
    dialog.setAttribute('aria-labelledby', 'goto-title');
    dialog.innerHTML = `
      <div class="goto-head">
        <h2 id="goto-title">Go to a page</h2>
        <button type="button" class="goto-close" aria-label="Close">×</button>
      </div>
      <input class="goto-input" type="text" role="combobox" aria-expanded="true" aria-controls="goto-list"
        aria-autocomplete="list" aria-label="Type a page, seat or switch" placeholder="Type a page, seat or switch" autocomplete="off" />
      <ul class="goto-list" id="goto-list" role="listbox" aria-label="Go to a page"></ul>
      <p class="goto-empty" hidden>Nothing matches.</p>`;
    document.body.appendChild(dialog);
    const input = dialog.querySelector('.goto-input');
    const list = dialog.querySelector('.goto-list');
    const empty = dialog.querySelector('.goto-empty');
    let shown = [];
    let active = 0;
    let timer = null;

    function paint() {
      list.textContent = '';
      shown.forEach((p, i) => {
        const li = document.createElement('li');
        li.id = `goto-${i}`;
        li.className = 'goto-item';
        li.setAttribute('role', 'option');
        li.setAttribute('aria-selected', String(i === active));
        const name = document.createElement('span');
        name.textContent = p.label;
        if (p.recent) {
          const tag = document.createElement('span');
          tag.className = 'goto-recent';
          tag.textContent = ' · recent';
          name.appendChild(tag);
        }
        const path = document.createElement('span');
        path.className = 'goto-path';
        path.textContent = p.run ? 'Action' : p.href;
        li.append(name, path);
        li.addEventListener('mouseenter', () => { active = i; mark(); });
        li.addEventListener('click', () => pick(p));
        list.appendChild(li);
      });
      list.hidden = !shown.length;
      empty.hidden = !!shown.length;
      mark();
    }
    function mark() {
      [...list.children].forEach((li, i) => li.setAttribute('aria-selected', String(i === active)));
      if (shown.length) {
        input.setAttribute('aria-activedescendant', `goto-${active}`);
        list.children[active].scrollIntoView({ block: 'nearest' });
      } else input.removeAttribute('aria-activedescendant');
    }
    async function filter() {
      const all = await load();
      const q = fold(input.value.trim());
      const here = location.pathname;
      const last = recent().filter((h) => h !== here && all.some((p) => p.href === h)).slice(0, RECENT_MAX);
      if (!q) {
        const top = last.map((h) => ({ ...all.find((p) => p.href === h), recent: true }));
        shown = [...top, ...all.filter((p) => !last.includes(p.href))];
      } else {
        const byLabel = (p) => fold(p.label).includes(q);
        shown = all.filter((p) => byLabel(p) || p.href.includes(q))
          .sort((a, b) => Number(!byLabel(a)) - Number(!byLabel(b)));
        // Then what this page's buttons do (issue #254), only once typed.
        shown = [...shown, ...actions().filter(byLabel)];
      }
      active = 0;
      paint();
      clearTimeout(timer);
      // Seats, switches and players (#292) from the server (issue #252), once typing pauses.
      if (q.length >= 2) timer = setTimeout(() => findPlaces(input.value), 150);
    }
    async function findPlaces(text) {
      let body;
      try {
        const r = await fetch(`/api/pages/find?q=${encodeURIComponent(text.trim())}`, { credentials: 'same-origin' });
        body = r.ok ? await r.json() : { places: [] };
      } catch (_) { return; }
      if (input.value !== text || !(body.places || []).length) return;
      const kinds = { seat: 'Seat', switch: 'Switch', player: 'Player' };
      shown = [...shown, ...body.places.map((p) => ({ href: p.href, label: `${kinds[p.kind] || ''} ${p.name}`.trim() }))];
      paint();
    }
    function pick(item) {
      if (!item.run) return go(item.href);
      dialog.close();
      item.run();
    }
    function go(href) {
      dialog.close();
      location.assign(href);
    }

    input.addEventListener('input', filter);
    input.addEventListener('keydown', (e) => {
      if (!shown.length) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); active = (active + 1) % shown.length; mark(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); active = (active - 1 + shown.length) % shown.length; mark(); }
      else if (e.key === 'Enter') { e.preventDefault(); pick(shown[active]); }
    });
    dialog.querySelector('.goto-close').addEventListener('click', () => dialog.close());
    // A click on the backdrop (outside the box) closes it, like the other dialogs.
    dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
    dialog.filter = filter;
  }

  function open() {
    if (!dialog) build();
    if (dialog.open) return;
    const input = dialog.querySelector('.goto-input');
    input.value = '';
    dialog.showModal();
    input.focus();
    dialog.filter();
  }

  document.querySelectorAll('[data-goto]').forEach((slot) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `goto-btn ${slot.dataset.goto || 'btn btn-ghost'}`;
    btn.setAttribute('aria-keyshortcuts', 'Control+K Meta+K');
    btn.title = `Go to any page (${mac ? '⌘K' : 'Ctrl+K'})`;
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
      + '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>'
      + '<span class="goto-label">Go to</span>'
      + `<kbd class="goto-kbd">${mac ? '⌘K' : 'Ctrl K'}</kbd>`;
    btn.addEventListener('click', open);
    slot.replaceWith(btn);
  });

  // Capture phase: before the floor plan's own shortcuts, and even while a field has focus.
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      e.stopPropagation();
      open();
    }
  }, true);

  remember(location.pathname);
  window.floorGoTo = { open };
})();
