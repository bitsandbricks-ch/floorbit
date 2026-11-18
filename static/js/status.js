// Public Jinja pages (stats wall, brackets): shows each time in the
// reader's own time zone and language. The page swaps in fresh content every minute (refresh.js), which runs this again.
'use strict';

(function () {
  const today = new Date().toDateString();
  document.querySelectorAll('time[data-at]').forEach((el) => {
    const at = new Date(Number(el.dataset.at) * 1000);
    if (Number.isNaN(at.getTime())) return;
    const opts = { hour: '2-digit', minute: '2-digit' };
    if (at.toDateString() !== today) opts.weekday = 'short';
    el.dateTime = at.toISOString();
    el.textContent = at.toLocaleString(document.documentElement.lang || [], opts);
  });
})();
