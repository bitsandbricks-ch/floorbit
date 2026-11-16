/* Shared dropdown for the Jinja pages (the React pages use frontend/src/components/ui/).
 *
 * It upgrades a native <select> in place: the select stays in the DOM, hidden, and remains the
 * source of truth, so code that reads .value, sets .value or listens for 'change' keeps working.
 * The button and list only mirror it. Opt out with <select data-native>.
 *
 *   UI.select(el, {search})   upgrade one select (search: true, false or 'auto' = more than 8 options)
 *   UI.enhanceSelects(root)   upgrade every select under root; new selects are upgraded by themselves
 *   UI.fillSelect(el, options, {current, includeUsed, placeholder})
 *                             fill from /api/options answers: free first, used ones hidden unless
 *                             includeUsed, the current value always kept
 */
(function () {
  'use strict';
  const UI = window.UI = window.UI || {};
  const valueDesc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
  const indexDesc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'selectedIndex');
  let open = null;   // the one open dropdown
  let seq = 0;

  // German for the few words the kit says itself (same language pick as the editor: panels.js).
  const DE = {'Search…': 'Suchen …', 'Search': 'Suchen', 'Nothing matches': 'Nichts gefunden', 'in use': 'belegt'};
  UI.lang = UI.lang || (() => {
    let lang = '';
    try { lang = localStorage.getItem('floorbit-lang') || ''; } catch { /* storage blocked */ }
    lang = lang || (navigator.languages || [navigator.language || 'en'])[0] || 'en';
    return lang.toLowerCase().startsWith('de') ? 'de' : 'en';
  });
  const t = (s) => (UI.lang() === 'de' && DE[s]) || s;
  const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  function chevron() {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 16 16'); svg.setAttribute('aria-hidden', 'true');
    svg.classList.add('ui-select-chevron');
    const p = document.createElementNS(ns, 'path');
    p.setAttribute('d', 'M4 6l4 4 4-4');
    svg.appendChild(p);
    return svg;
  }

  class Select {
    constructor(el, opts) {
      this.el = el;
      this.opts = Object.assign({search: 'auto'}, opts || {});
      this.id = `ui-select-${++seq}`;
      this.active = -1;
      this.query = '';
      this.typed = ''; this.typedAt = 0;

      const btn = this.btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ui-select';
      for (const c of el.classList) if (c !== 'modal-input' && c !== 'hidden') btn.classList.add(c);
      if (el.classList.contains('modal-input')) btn.classList.add('ui-select-block');
      btn.setAttribute('aria-haspopup', 'listbox');
      btn.setAttribute('aria-expanded', 'false');
      btn.setAttribute('aria-controls', `${this.id}-list`);
      this.labelEl = document.createElement('span');
      this.labelEl.className = 'ui-select-label';
      btn.append(this.labelEl, chevron());
      el.after(btn);
      el.classList.add('ui-select-native');
      el.tabIndex = -1;
      el.setAttribute('aria-hidden', 'true');

      // A <label for=select> should focus and name the button.
      if (el.id) {
        const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (lab) {
          lab.id = lab.id || `${this.id}-label`;
          btn.setAttribute('aria-labelledby', `${lab.id} ${this.id}-value`);
          lab.addEventListener('click', (e) => { e.preventDefault(); btn.focus(); });
        }
      }
      this.labelEl.id = `${this.id}-value`;
      if (!btn.hasAttribute('aria-labelledby') && el.getAttribute('aria-label')) btn.setAttribute('aria-label', el.getAttribute('aria-label'));
      if (el.title) btn.title = el.title;

      btn.addEventListener('click', () => (open === this ? this.close() : this.open()));
      btn.addEventListener('keydown', (e) => this.onButtonKey(e));

      // Keep the button in step with the select: options, disabled, hidden and value.
      this.mo = new MutationObserver(() => this.sync());
      this.mo.observe(el, {childList: true, subtree: true, characterData: true, attributes: true,
        attributeFilter: ['disabled', 'class', 'hidden', 'label', 'selected', 'style', 'title']});
      el.addEventListener('change', () => this.sync());
      const self = this;
      Object.defineProperty(el, 'value', {
        configurable: true,
        get() { return valueDesc.get.call(this); },
        set(v) { valueDesc.set.call(this, v); self.sync(); },
      });
      Object.defineProperty(el, 'selectedIndex', {
        configurable: true,
        get() { return indexDesc.get.call(this); },
        set(v) { indexDesc.set.call(this, v); self.sync(); },
      });
      el.uiSelect = this;
      this.sync();
    }

    items() {
      const out = [];
      for (const node of this.el.children) {
        if (node.tagName === 'OPTGROUP') {
          for (const o of node.children) out.push({o, group: node.label, disabled: o.disabled || node.disabled});
        } else if (node.tagName === 'OPTION') out.push({o: node, group: '', disabled: node.disabled});
      }
      return out.filter((it) => !it.o.hidden);
    }

    sync() {
      const el = this.el, btn = this.btn;
      const cur = el.options[indexDesc.get.call(el)];
      this.labelEl.textContent = cur ? cur.textContent : (el.dataset.placeholder || '');
      btn.classList.toggle('is-placeholder', !cur || cur.value === '' && !!el.dataset.placeholder);
      btn.disabled = el.disabled;
      btn.classList.toggle('hidden', el.classList.contains('hidden'));
      btn.hidden = el.hidden;
      if (el.style.display === 'none') btn.style.display = 'none'; else btn.style.removeProperty('display');
      if (open === this) this.renderList();
    }

    searchOn() {
      const s = this.opts.search ?? this.el.dataset.search;
      if (s === true || s === 'true') return true;
      if (s === false || s === 'false') return false;
      return this.items().length > 8;
    }

    open() {
      if (this.el.disabled) return;
      if (open) open.close();
      open = this;
      this.query = '';
      const pop = this.pop = document.createElement('div');
      pop.className = 'ui-pop ui-select-pop';
      if (this.searchOn()) {
        const s = this.searchEl = document.createElement('input');
        s.type = 'search'; s.className = 'ui-select-search';
        s.placeholder = t('Search…'); s.setAttribute('aria-label', t('Search'));
        s.setAttribute('aria-controls', `${this.id}-list`);
        s.setAttribute('aria-autocomplete', 'list');
        s.addEventListener('input', () => { this.query = s.value; this.active = -1; this.renderList(); });
        s.addEventListener('keydown', (e) => this.onListKey(e));
        pop.appendChild(s);
      } else this.searchEl = null;
      const list = this.list = document.createElement('div');
      list.className = 'ui-select-list';
      list.id = `${this.id}-list`;
      list.setAttribute('role', 'listbox');
      list.tabIndex = -1;
      list.addEventListener('keydown', (e) => this.onListKey(e));
      list.addEventListener('mousedown', (e) => e.preventDefault());   // keep focus where it is
      list.addEventListener('click', (e) => {
        const row = e.target.closest('.ui-option');
        if (row && !row.classList.contains('is-disabled')) this.choose(+row.dataset.index);
      });
      list.addEventListener('mousemove', (e) => {
        const row = e.target.closest('.ui-option');
        if (row && +row.dataset.pos !== this.active) this.setActive(+row.dataset.pos, false);
      });
      pop.appendChild(list);
      // Inside an open <dialog> the popover has to live in it to stay above the backdrop.
      (this.btn.closest('dialog[open]') || document.body).appendChild(pop);
      this.btn.setAttribute('aria-expanded', 'true');
      this.btn.classList.add('is-open');
      this.renderList();
      const selPos = this.visible.findIndex((it) => it.o.selected);
      this.setActive(selPos >= 0 ? selPos : this.firstEnabled(0, 1), true);
      this.place();
      (this.searchEl || this.list).focus({preventScroll: true});
      requestAnimationFrame(() => pop.classList.add('is-in'));
    }

    place() {
      const r = this.btn.getBoundingClientRect();
      const pop = this.pop;
      const vw = window.innerWidth, vh = window.innerHeight;
      pop.style.minWidth = `${Math.max(r.width, 160)}px`;
      pop.style.maxWidth = `${Math.min(Math.max(r.width, 320), vw - 16)}px`;
      const below = vh - r.bottom - 8, above = r.top - 8;
      const up = below < 220 && above > below;
      const room = Math.max(120, Math.min(up ? above : below, 360));
      pop.style.maxHeight = `${room}px`;
      const h = Math.min(pop.scrollHeight, room);
      const left = Math.min(Math.max(8, r.left), vw - pop.offsetWidth - 8);
      pop.style.left = `${left}px`;
      pop.style.top = `${up ? r.top - h - 4 : r.bottom + 4}px`;
      pop.classList.toggle('is-up', up);
    }

    close(refocus = true) {
      if (open !== this) return;
      open = null;
      this.pop?.remove();
      this.pop = this.list = this.searchEl = null;
      this.btn.setAttribute('aria-expanded', 'false');
      this.btn.classList.remove('is-open');
      if (refocus) this.btn.focus({preventScroll: true});
    }

    renderList() {
      if (!this.list) return;
      const q = norm(this.query);
      const all = this.items().map((it, i) => Object.assign(it, {index: i}));
      this.visible = q ? all.filter((it) => norm(it.o.textContent + ' ' + it.o.value + ' ' + (it.o.dataset.hint || '')).includes(q)) : all;
      const list = this.list;
      list.textContent = '';
      let group = null;
      this.visible.forEach((it, pos) => {
        if (it.group && it.group !== group) {
          const g = document.createElement('div');
          g.className = 'ui-option-group';
          g.textContent = it.group;
          g.setAttribute('role', 'presentation');
          list.appendChild(g);
        }
        group = it.group;
        const row = document.createElement('div');
        row.className = 'ui-option';
        row.id = `${this.id}-o${pos}`;
        row.setAttribute('role', 'option');
        row.dataset.index = it.index;
        row.dataset.pos = pos;
        row.setAttribute('aria-selected', it.o.selected ? 'true' : 'false');
        if (it.disabled) { row.classList.add('is-disabled'); row.setAttribute('aria-disabled', 'true'); }
        const label = document.createElement('span');
        label.className = 'ui-option-label';
        label.textContent = it.o.textContent;
        row.appendChild(label);
        if (it.o.dataset.hint) {
          const hint = document.createElement('span');
          hint.className = 'ui-option-hint';
          hint.textContent = it.o.dataset.hint;
          row.appendChild(hint);
        }
        list.appendChild(row);
      });
      if (!this.visible.length) {
        const none = document.createElement('div');
        none.className = 'ui-option-empty';
        none.textContent = t('Nothing matches');
        list.appendChild(none);
      }
      if (this.active >= this.visible.length) this.active = -1;
      this.setActive(this.active, false);
    }

    firstEnabled(from, step) {
      const v = this.visible || [];
      for (let i = from; i >= 0 && i < v.length; i += step) if (!v[i].disabled) return i;
      return -1;
    }

    setActive(pos, scroll) {
      this.active = pos;
      if (!this.list) return;
      for (const row of this.list.querySelectorAll('.ui-option.is-active')) row.classList.remove('is-active');
      const row = pos >= 0 ? this.list.querySelector(`[data-pos="${pos}"]`) : null;
      const owner = this.searchEl || this.list;
      if (row) {
        row.classList.add('is-active');
        owner.setAttribute('aria-activedescendant', row.id);
        if (scroll) row.scrollIntoView({block: 'nearest'});
      } else owner.removeAttribute('aria-activedescendant');
    }

    move(step) {
      const v = this.visible || [];
      if (!v.length) return;
      let next = this.firstEnabled(this.active + step, step);
      if (next < 0) next = this.firstEnabled(step > 0 ? 0 : v.length - 1, step);
      this.setActive(next, true);
    }

    choose(index) {
      const el = this.el;
      const before = indexDesc.get.call(el);
      const opt = this.items()[index]?.o;
      if (!opt) return;
      indexDesc.set.call(el, Array.prototype.indexOf.call(el.options, opt));
      this.close();
      this.sync();
      if (indexDesc.get.call(el) !== before) {
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
      }
    }

    typeahead(ch) {
      const now = Date.now();
      this.typed = (now - this.typedAt > 700 ? '' : this.typed) + ch.toLowerCase();
      this.typedAt = now;
      const items = this.items();
      const start = Math.max(0, indexDesc.get.call(this.el));
      for (let k = 1; k <= items.length; k++) {
        const it = items[(start + k - (this.typed.length > 1 ? 1 : 0)) % items.length];
        if (!it.disabled && norm(it.o.textContent).startsWith(this.typed)) return it;
      }
      return null;
    }

    onButtonKey(e) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key) && !e.altKey) {
        e.preventDefault(); e.stopPropagation();
        this.open();
      } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        // Typing on the closed button picks the matching option, as a native select does.
        // Only when something matches, so page shortcuts still work with the button focused.
        const it = this.typeahead(e.key);
        if (it) { e.preventDefault(); e.stopPropagation(); this.choose(this.items().indexOf(it)); }
      }
    }

    onListKey(e) {
      e.stopPropagation();   // the editor's shortcuts must not fire while the list is open
      const v = this.visible || [];
      switch (e.key) {
        case 'ArrowDown': e.preventDefault(); this.move(1); break;
        case 'ArrowUp': e.preventDefault(); this.move(-1); break;
        case 'Home': if (!this.searchEl) { e.preventDefault(); this.setActive(this.firstEnabled(0, 1), true); } break;
        case 'End': if (!this.searchEl) { e.preventDefault(); this.setActive(this.firstEnabled(v.length - 1, -1), true); } break;
        case 'PageDown': e.preventDefault(); for (let i = 0; i < 8; i++) this.move(1); break;
        case 'PageUp': e.preventDefault(); for (let i = 0; i < 8; i++) this.move(-1); break;
        case 'Enter': e.preventDefault(); if (v[this.active]) this.choose(v[this.active].index); break;
        case 'Escape': e.preventDefault(); this.close(); break;
        case 'Tab': this.close(false); break;
        default:
          if (!this.searchEl && e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
            const it = this.typeahead(e.key);
            if (it) this.setActive(v.indexOf(it), true);
          }
      }
    }
  }

  UI.select = function (el, opts) {
    if (!el || el.uiSelect || el.multiple || el.size > 1 || el.hasAttribute('data-native')) return el?.uiSelect || null;
    return new Select(el, opts);
  };

  UI.enhanceSelects = function (root = document) {
    if (root.matches?.('select')) UI.select(root);
    root.querySelectorAll?.('select').forEach((s) => UI.select(s));
  };

  UI.fillSelect = function (el, options, {current = el.value, includeUsed = false, placeholder = null} = {}) {
    el.textContent = '';
    if (placeholder != null) el.add(new Option(placeholder, ''));
    const groups = new Map();
    for (const o of options || []) {
      if (o.used && !includeUsed && String(o.value) !== String(current)) continue;
      const opt = new Option(o.label ?? o.value, o.value);
      const hint = o.used ? `${t('in use')}: ${o.used}` : (o.hint || '');
      if (hint) opt.dataset.hint = hint;
      if (o.used) opt.dataset.used = o.used;
      let parent = el;
      if (o.group) {
        if (!groups.has(o.group)) {
          const g = document.createElement('optgroup');
          g.label = o.group;
          groups.set(o.group, g);
          el.appendChild(g);
        }
        parent = groups.get(o.group);
      }
      parent.appendChild(opt);
    }
    if (current != null && current !== '' && ![...el.options].some((o) => o.value === String(current))) {
      el.add(new Option(String(current), String(current)));   // keep a value the source no longer lists
    }
    el.value = current ?? '';
    return el;
  };

  // One open dropdown at a time; clicks outside, scrolling the page and resizing close it.
  document.addEventListener('pointerdown', (e) => {
    if (open && !open.pop.contains(e.target) && !open.btn.contains(e.target)) open.close(false);
  }, true);
  window.addEventListener('resize', () => open?.close(false));
  document.addEventListener('scroll', (e) => {
    if (open && !open.pop.contains(e.target)) open.close(false);
  }, true);

  function boot() {
    UI.enhanceSelects(document);
    new MutationObserver((records) => {
      for (const r of records) for (const n of r.addedNodes) if (n.nodeType === 1) UI.enhanceSelects(n);
    }).observe(document.body, {childList: true, subtree: true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
