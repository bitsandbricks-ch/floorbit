// The public schedule page (templates/agenda.html, docs/schedule.md): times in the reader's own
// time zone and language, a heading for each day, the countdown ticking every second. The page
// reloads itself every minute (meta refresh) for anything new.
'use strict';

(function () {
  const lang = document.documentElement.lang || [];
  const today = new Date().toDateString();
  document.querySelectorAll('time[data-at]').forEach((el) => {
    const at = new Date(Number(el.dataset.at) * 1000);
    if (Number.isNaN(at.getTime())) return;
    const opts = { hour: '2-digit', minute: '2-digit' };
    if (at.toDateString() !== today && !el.closest('#programme')) opts.weekday = 'short';
    el.dateTime = at.toISOString();
    el.textContent = at.toLocaleString(lang, opts);
  });

  // A heading before the first item of each day, in the reader's time zone.
  let day = null;
  document.querySelectorAll('#programme li[data-at]').forEach((li) => {
    const at = new Date(Number(li.dataset.at) * 1000);
    const key = at.toDateString();
    if (key === day) return;
    day = key;
    const h = document.createElement('li');
    h.className = 'day';
    h.textContent = at.toLocaleDateString(lang, { weekday: 'long', day: 'numeric', month: 'long' });
    li.before(h);
  });

  const box = document.getElementById('countdown');
  if (!box) return;
  // Count from the server's clock, so a screen with a wrong clock still shows the right time left.
  const skew = Number(box.dataset.now) * 1000 - Date.now();
  const target = Number(box.dataset.target) * 1000;
  const pad = (n) => String(n).padStart(2, '0');
  const tick = () => {
    let left = Math.max(0, Math.floor((target - (Date.now() + skew)) / 1000));
    const d = Math.floor(left / 86400); left -= d * 86400;
    const h = Math.floor(left / 3600); left -= h * 3600;
    const m = Math.floor(left / 60);
    const parts = { d: String(d), h: pad(h), m: pad(m), s: pad(left - m * 60) };
    box.querySelectorAll('[data-unit]').forEach((el) => { el.textContent = parts[el.dataset.unit]; });
  };
  tick();
  window.setInterval(tick, 1000);
})();
