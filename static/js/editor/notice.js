// Floor plan editor: the crew notice under the top bar (issue #246), the same one the React
// pages show. Leads put it up from the user menu on those pages; here it is only shown.
// Classic script sharing one global scope with the other editor/*.js files (see README.md).
'use strict';

const NOTICE_HIDDEN_KEY = 'floorbit-notice-hidden';

function noticeTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

async function loadNotice() {
  const box = document.getElementById('crew-notice');
  if (!box) return;
  let notice = null;
  try {
    notice = (await api('GET', '/api/notice')).notice;
  } catch {
    return;   // extra information; the floor plan works without it
  }
  let hidden = null;
  try { hidden = Number(localStorage.getItem(NOTICE_HIDDEN_KEY)) || null; } catch { /* private mode */ }
  if (!notice || hidden === notice.at) {
    box.hidden = true;
    return;
  }
  box.classList.toggle('crew-notice-warn', notice.level === 'warn');
  box.querySelector('.crew-notice-text').textContent = notice.text;
  box.querySelector('.crew-notice-meta').textContent = [
    notice.by ? `${notice.by}, ${noticeTime(notice.at)}` : noticeTime(notice.at),
    notice.until ? `until ${noticeTime(notice.until)}` : '',
  ].filter(Boolean).join(' · ');
  box.querySelector('.crew-notice-hide').onclick = () => {
    try { localStorage.setItem(NOTICE_HIDDEN_KEY, String(notice.at)); } catch { /* private mode */ }
    box.hidden = true;
  };
  box.hidden = false;
}

window.addEventListener('lal:live', (e) => {
  if (e.detail && e.detail.type === 'notice.changed') loadNotice();
});
// The notice may end on its own (until): look again now and then.
setInterval(() => { if (!document.hidden) loadNotice(); }, 60000);
