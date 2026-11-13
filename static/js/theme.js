'use strict';

// ── Colour theme ─────────────────────────────────────────────────────────────
// Loaded in <head> on every page so the theme is set before the first paint
// (no dark flash on a light page). The choice is saved per browser; with
// nothing saved the page follows the operating system's light/dark setting.
// Any button with a data-theme-toggle attribute switches between the two.
(function () {
  const KEY = 'theme';
  const media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;

  function saved() {
    try {
      const v = localStorage.getItem(KEY);
      return v === 'light' || v === 'dark' ? v : null;
    } catch { return null; }
  }
  function current() {
    return saved() || (media && media.matches ? 'light' : 'dark');
  }

  function syncButtons() {
    const light = current() === 'light';
    const label = light ? 'Switch to dark theme' : 'Switch to light theme';
    document.querySelectorAll('[data-theme-toggle]').forEach((btn) => {
      const shortcut = btn.dataset.themeShortcut;
      btn.title = shortcut ? `${label} (${shortcut})` : label;
      btn.setAttribute('aria-label', label);
    });
  }

  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    syncButtons();
    document.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
  }

  function set(theme) {
    try { localStorage.setItem(KEY, theme); } catch { /* storage unavailable */ }
    apply(theme);
  }
  function toggle() {
    const next = current() === 'light' ? 'dark' : 'light';
    set(next);
    return next;
  }

  apply(current());

  // Follow the OS setting while the user hasn't picked one
  if (media && media.addEventListener) {
    media.addEventListener('change', () => { if (!saved()) apply(current()); });
  }
  // Keep other open tabs (floor plan, settings) in step
  window.addEventListener('storage', (e) => { if (e.key === KEY) apply(current()); });

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-theme-toggle]').forEach((btn) => btn.addEventListener('click', toggle));
    syncButtons();
  });

  window.floorTheme = { current, set, toggle };
})();
