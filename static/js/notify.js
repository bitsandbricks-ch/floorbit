// Browser notifications for the crew (issue #154). Opt-in per device: a new incident, a job sent to
// me, a switch going down. Only while a Floorbit tab is open (no push service): it listens to the
// same live events stream as the pages. Loaded by the floor plan editor and the React pages; the
// React user menu changes the settings through window.floorNotify.
'use strict';

(function () {
  const KEY = 'floorbit-notify';
  const DEFAULTS = { on: false, incidents: true, jobs: true, switches: true, services: true,
                     quiet: false, quietFrom: '22:00', quietTo: '08:00', jobsInQuiet: true, watch: [] };
  let source = null;
  let me = null;

  // The React pages keep the language in floorbit-lang; the editor follows the browser.
  const TEXTS = {
    en: { incident: 'New incident', seat: 'Seat', sw: 'Switch', job: 'A job for you', jobText: 'An incident was sent to you.',
          down: 'Switch down', downText: '{name} went offline.', service: 'Service down',
          watched: 'Watched seat', seatDown: 'Seat {seat} went offline.', seatUp: 'Seat {seat} is online again.' },
    de: { incident: 'Neue Störung', seat: 'Platz', sw: 'Switch', job: 'Ein Auftrag für dich', jobText: 'Dir wurde eine Störung zugeteilt.',
          down: 'Switch ausgefallen', downText: '{name} ist offline.', service: 'Dienst ausgefallen',
          watched: 'Beobachteter Platz', seatDown: 'Platz {seat} ist offline.', seatUp: 'Platz {seat} ist wieder online.' },
  };
  function text() {
    let lang = '';
    try { lang = localStorage.getItem('floorbit-lang') || ''; } catch { /* storage blocked */ }
    lang = lang || (navigator.languages || [navigator.language || 'en'])[0] || 'en';
    return TEXTS[lang.toLowerCase().startsWith('de') ? 'de' : 'en'];
  }

  function read() {
    try {
      return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(KEY)) || {}) };
    } catch {
      return { ...DEFAULTS };
    }
  }

  function minutes(hhmm) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || ''));
    return m ? (Number(m[1]) % 24) * 60 + Number(m[2]) : null;
  }

  // Quiet hours (issue #161): local time on this device, and they may run past midnight.
  function quietNow(s, date) {
    if (!s.quiet) return false;
    const from = minutes(s.quietFrom);
    const to = minutes(s.quietTo);
    if (from === null || to === null || from === to) return false;
    const d = date || new Date();
    const now = d.getHours() * 60 + d.getMinutes();
    return from < to ? now >= from && now < to : now >= from || now < to;
  }

  function supported() {
    return typeof Notification !== 'undefined' && typeof EventSource !== 'undefined';
  }

  function show(title, body, tag, url) {
    if (Notification.permission !== 'granted') return;
    // The same tag in several open tabs shows one notification, not one per tab.
    const n = new Notification(title, { body, tag, icon: '/static/brand/apple-icon.png' });
    n.onclick = () => {
      window.focus();
      if (url) location.href = url;
      n.close();
    };
  }

  async function json(path) {
    const r = await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  }

  async function onIncident(data) {
    const s = read();
    if (!s.incidents || quietNow(s) || data.action !== 'created' || !data.id) return;
    let item = null;
    try {
      item = ((await json('/api/incidents')).incidents || []).find((i) => i.id === data.id);
    } catch {
      return;   // no incident board for this account
    }
    if (!item) return;
    const t = text();
    const where = item.seat ? `${t.seat} ${item.seat}` : item.switch ? `${t.sw} ${item.switch}` : '';
    show(t.incident, [where, item.title].filter(Boolean).join(': '), `incident-${item.id}`, '/incidents');
  }

  function onDispatched(data) {
    const s = read();
    if (!s.jobs || (quietNow(s) && !s.jobsInQuiet) || !me || data.assignee !== me) return;
    show(text().job, text().jobText, `job-${data.id}`, '/jobs');
  }

  // A mute means "stop paging me about this" (issue #282). If the list can't be read, notify anyway.
  async function muted(key) {
    try {
      return ((await json('/api/problems')).mutes || []).some((m) => m.switch_id === key);
    } catch {
      return false;
    }
  }

  async function onSwitch(data) {
    const s = read();
    if (!s.switches || quietNow(s) || !data || data.status !== 'offline') return;
    if (data.id && await muted(String(data.id))) return;
    show(text().down, text().downText.replace('{name}', data.name || 'Switch'), `switch-${data.id || data.name}`, '/');
  }

  // The health wall only sends confirmed changes, so a blip doesn't notify (issue #282).
  async function onHealth(data) {
    const s = read();
    if (!s.services || quietNow(s) || !Array.isArray(data.changes)) return;
    for (const c of data.changes) {
      if (c.status !== 'down' || c.previous === 'down' || await muted(`health:${c.id}`)) continue;
      show(text().service, [c.name, c.summary].filter(Boolean).join(': '), `health-${c.id}`, '/health');
    }
  }

  // Watched seats (issue #178): like a job sent to me, they come through quiet hours unless that is off.
  function onSeats(data) {
    const s = read();
    const watch = Array.isArray(s.watch) ? s.watch : [];
    if (!watch.length || (quietNow(s) && !s.jobsInQuiet) || !Array.isArray(data.seats)) return;
    const t = text();
    for (const [seat, on] of data.seats) {
      if (!watch.includes(seat)) continue;
      show(t.watched, (on ? t.seatUp : t.seatDown).replace('{seat}', seat), `seat-${seat}`, `/plan?seat=${encodeURIComponent(seat)}`);
    }
  }

  function listen(type, fn) {
    source.addEventListener(type, (e) => {
      try {
        fn(JSON.parse(e.data).data || {});
      } catch {
        // not one of ours
      }
    });
  }

  async function start() {
    stop();
    const s = read();
    if (!s.on || !supported() || Notification.permission !== 'granted') return;
    try {
      const who = await json('/api/auth/me');
      me = who.user ? who.user.username : null;
    } catch {
      me = null;
    }
    source = new EventSource('/api/events');
    listen('incident.changed', onIncident);
    listen('incident.dispatched', onDispatched);
    listen('switch.status', onSwitch);
    listen('health.changed', onHealth);
    listen('seats.changed', onSeats);
  }

  function stop() {
    if (source) source.close();
    source = null;
  }

  async function set(changes) {
    const next = { ...read(), ...changes };
    if (changes.on && supported() && Notification.permission === 'default') {
      next.on = (await Notification.requestPermission()) === 'granted';
    }
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      // storage blocked: works until the tab closes
    }
    start();
    return next;
  }

  window.floorNotify = {
    supported,
    settings: read,
    permission: () => (supported() ? Notification.permission : 'unsupported'),
    quietNow: () => quietNow(read()),
    set,
  };
  // Another tab changed the settings.
  window.addEventListener('storage', (e) => { if (e.key === KEY) start(); });
  start();
})();
