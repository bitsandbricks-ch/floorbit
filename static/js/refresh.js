// Keeps a public page current without reloading it (issue #290): the status page, stats wall,
// schedule and bracket. Every data-every seconds it fetches the same address and swaps in the new
// <main>, so a big screen doesn't flash white, and if the server or network is gone for a moment
// it keeps showing the last good data with a small note instead of a browser error page.
// Without JavaScript the <noscript> meta refresh in the page does the job.
'use strict';

(function () {
  const me = document.currentScript;
  const every = Math.max(10, Number(me && me.dataset.every) || 60) * 1000;
  const TEXTS = {
    en: 'No connection. Showing data from {time}.',
    de: 'Keine Verbindung. Daten von {time}.',
  };
  let lastGood = Date.now();
  let timer = null;

  function note(show) {
    let el = document.getElementById('refresh-stale');
    if (!show) {
      if (el) el.remove();
      return;
    }
    if (!el) {
      el = document.createElement('p');
      el.id = 'refresh-stale';
      el.setAttribute('role', 'status');
      el.style.cssText = 'position:fixed;left:50%;top:12px;transform:translateX(-50%);margin:0;padding:6px 14px;'
        + 'border-radius:999px;border:1px solid var(--color-warn);background:var(--color-surface);color:var(--color-fg);'
        + 'font:600 14px/1.4 var(--font-sans);z-index:10;';
      document.body.append(el);
    }
    const lang = document.documentElement.lang || 'en';
    const time = new Date(lastGood).toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    el.textContent = TEXTS[lang.toLowerCase().startsWith('de') ? 'de' : 'en'].replace('{time}', time);
  }

  // Scripts that arrive with the new <main> are inert; add them again so they run (local times,
  // the countdown).
  function rerun(main) {
    main.querySelectorAll('script').forEach((old) => {
      const s = document.createElement('script');
      if (old.src) s.src = old.src; else s.textContent = old.textContent;
      old.replaceWith(s);
    });
  }

  async function refresh() {
    try {
      const r = await fetch(location.href, { cache: 'no-store', credentials: 'same-origin', headers: { Accept: 'text/html' } });
      const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
      const fresh = doc.querySelector('main');
      const current = document.querySelector('main');
      // A page that was switched off answers 404 with its "switched off" text: show that too.
      if (!fresh || !current) throw new Error('no main');
      const main = document.importNode(fresh, true);
      current.replaceWith(main);
      rerun(main);
      lastGood = Date.now();
      note(false);
    } catch {
      note(true);
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      // A hidden tab waits; it refreshes as soon as it is shown again.
      if (!document.hidden) await refresh();
      schedule();
    }, every);
  }

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && Date.now() - lastGood > every) refresh().then(schedule);
  });
  schedule();
})();
