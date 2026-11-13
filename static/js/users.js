'use strict';

// Users page: list accounts, change roles, reset passwords, add and remove.
(function () {
  const list = document.getElementById('us-list');
  const addForm = document.getElementById('us-add');
  const addRole = document.getElementById('us-add-role');
  const addMsg = document.getElementById('us-add-msg');
  const rolesIntro = document.getElementById('us-roles');
  let state = { users: [], roles: [], me: null };

  async function api(method, path, body) {
    const resp = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    return data;
  }

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') node.className = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) node.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children) node.append(c);
    return node;
  }

  function setMsg(node, text, kind) {
    node.textContent = text || '';
    node.className = 'us-msg' + (kind ? ' ' + kind : '');
  }

  function roleSelect(value, disabled, onchange) {
    const sel = el('select', { disabled, 'aria-label': 'Role', onchange });
    for (const r of state.roles) sel.append(el('option', { value: r.id, selected: r.id === value }, r.label));
    return sel;
  }

  function row(user) {
    const isMe = user.username === state.me;
    const msg = el('span', { class: 'us-msg', role: 'status' });
    const pw = el('input', { type: 'password', placeholder: 'New password, at least 8 characters', autocomplete: 'new-password', 'aria-label': 'New password' });
    const reset = el('div', { class: 'us-reset', hidden: true },
      pw,
      el('button', { class: 'st-btn st-btn-primary', type: 'button', onclick: async () => {
        try {
          await api('PATCH', `/api/users/${encodeURIComponent(user.username)}`, { password: pw.value });
          if (isMe) { location.assign('/login'); return; }
          reset.hidden = true; pw.value = '';
          setMsg(msg, 'Password changed.', 'ok');
        } catch (e) { setMsg(msg, e.message, 'error'); }
      } }, 'Save'));

    let armed = false;
    const remove = el('button', { class: 'st-btn st-btn-danger', type: 'button', disabled: isMe,
      title: isMe ? 'You cannot remove your own account' : 'Remove this account',
      onclick: async () => {
        if (!armed) {
          armed = true; remove.classList.add('armed'); remove.textContent = 'Click to confirm';
          setTimeout(() => { armed = false; remove.classList.remove('armed'); remove.textContent = 'Remove'; }, 4000);
          return;
        }
        try { render(await api('DELETE', `/api/users/${encodeURIComponent(user.username)}`)); }
        catch (e) { setMsg(msg, e.message, 'error'); }
      } }, 'Remove');

    const select = roleSelect(user.role, isMe, async (ev) => {
      try {
        render(await api('PATCH', `/api/users/${encodeURIComponent(user.username)}`, { role: ev.target.value }));
      } catch (e) { ev.target.value = user.role; setMsg(msg, e.message, 'error'); }
    });
    if (isMe) select.title = 'Ask another admin to change your role';

    const extra = user.identities.length ? ` · linked: ${user.identities.join(', ')}` : '';
    return el('div', { class: 'us-row' },
      el('div', { class: 'us-who' },
        el('strong', {}, user.display_name, isMe ? el('span', { class: 'us-you' }, 'you') : ''),
        el('small', {}, user.username + extra)),
      select,
      el('div', { class: 'us-actions' },
        el('button', { class: 'st-btn', type: 'button', onclick: () => { reset.hidden = !reset.hidden; if (!reset.hidden) pw.focus(); } },
          'Reset password'),
        remove),
      reset, msg);
  }

  function render(data) {
    state = data;
    list.replaceChildren(...state.users.map(row));
    if (!addRole.options.length) {
      for (const r of state.roles) addRole.append(el('option', { value: r.id, selected: r.id === 'editor' }, r.label));
      rolesIntro.replaceChildren(...state.roles.flatMap((r, i) => [
        i ? ' ' : '', el('strong', {}, r.label + ':'), ' ' + r.description]));
    }
  }

  addForm.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const body = Object.fromEntries(new FormData(addForm));
    try {
      render(await api('POST', '/api/users', body));
      setMsg(addMsg, `Added ${body.username}.`, 'ok');
      addForm.reset(); addRole.value = 'editor';
    } catch (e) { setMsg(addMsg, e.message, 'error'); }
  });

  api('GET', '/api/users').then(render).catch((e) => setMsg(addMsg, e.message, 'error'));
})();
