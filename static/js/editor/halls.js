// Floor plan editor: halls (issue #20). Each hall has its own plan, background image, switches and
// seat blocks; the editor shows one at a time (?hall=<id>, remembered per browser). The Halls dialog
// adds, renames and deletes halls, sets the background and imports seat blocks from a CSV file.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

let halls = [];
let currentHall = null;

const hallSelect = $('hall-select');
const hallsBackdrop = $('halls-backdrop');
const hallsList = $('halls-list');
const planBg = $('plan-bg');

// Placed items of this hall; unplaced switches belong to no hall, so every hall's list offers them.
function inHall(items) {
  return items.filter(i => i.placed === false || i.hall_id === currentHall);
}

async function loadHalls() {
  try {
    halls = (await api('GET', '/api/halls')).halls;
  } catch {
    halls = [{ id: 'main', name: 'Hall', background: null }];
  }
  const wanted = new URLSearchParams(location.search).get('hall') || readJSON('hall', null);
  currentHall = (halls.find(h => h.id === wanted) || halls[0]).id;
  writeJSON('hall', currentHall);
  renderHallPicker();
  renderBackground();
}

function hallById(id) { return halls.find(h => h.id === id); }

function renderHallPicker() {
  hallSelect.replaceChildren(...halls.map((h) => {
    const opt = document.createElement('option');
    opt.value = h.id;
    opt.textContent = h.name;
    opt.selected = h.id === currentHall;
    return opt;
  }));
  hallSelect.title = 'Hall shown on the plan';
}

function renderBackground() {
  const hall = hallById(currentHall);
  planBg.hidden = !(hall && hall.background);
  if (hall && hall.background) planBg.src = hall.background;
  else planBg.removeAttribute('src');
}

function goToHall(id) {
  const url = new URL(location.href);
  url.searchParams.set('hall', id);
  url.searchParams.delete('seat');
  url.searchParams.delete('switch');
  writeJSON('hall', id);
  location.href = url.toString();   // a fresh load: every layer then reads only this hall
}

hallSelect.addEventListener('change', () => goToHall(hallSelect.value));

// ── The Halls dialog ─────────────────────────────────────────────────────────────────────
function readFile(input, asText) {
  return new Promise((resolve, reject) => {
    const file = input.files && input.files[0];
    if (!file) { resolve(null); return; }
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    if (asText) reader.readAsText(file); else reader.readAsDataURL(file);
  });
}

function hallButton(label, onClick, cls = 'btn btn-ghost btn-sm') {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = cls;
  b.textContent = label;
  b.addEventListener('click', onClick);
  return b;
}

function filePicker(label, accept, onFile) {
  const wrap = document.createElement('label');
  wrap.className = 'btn btn-ghost btn-sm';
  wrap.textContent = label;
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = accept;
  input.hidden = true;
  input.addEventListener('change', async () => {
    try { await onFile(input); } finally { input.value = ''; }
  });
  wrap.append(input);
  return wrap;
}

async function refreshHalls() {
  halls = (await api('GET', '/api/halls')).halls;
  renderHallPicker();
  renderBackground();
  renderHallsDialog();
}

function renderHallsDialog() {
  hallsList.replaceChildren(...halls.map((h) => {
    const row = document.createElement('li');
    row.className = 'hall-row' + (h.id === currentHall ? ' is-current' : '');

    const name = document.createElement('input');
    name.className = 'modal-input';
    name.value = h.name;
    name.maxLength = 60;
    name.setAttribute('aria-label', 'Hall name');
    name.addEventListener('change', async () => {
      try { await api('PUT', `/api/halls/${h.id}`, { name: name.value }); await refreshHalls(); }
      catch (e) { toastError('Could not rename the hall', e); }
    });

    const info = document.createElement('span');
    info.className = 'field-hint';
    info.textContent = `${h.switches} switch(es), ${h.seat_blocks} seat block(s)` +
      (h.background ? ', background image' : '');

    const actions = document.createElement('div');
    actions.className = 'hall-actions';
    if (h.id !== currentHall) actions.append(hallButton('Open', () => goToHall(h.id)));
    actions.append(filePicker(h.background ? 'Replace background…' : 'Background image…',
      'image/png,image/jpeg,image/webp,image/svg+xml', async (input) => {
        const image = await readFile(input, false);
        if (!image) return;
        try {
          await api('PUT', `/api/halls/${h.id}/background`, { image });
          await refreshHalls();
          toast('Background set', { type: 'success' });
        } catch (e) { toastError('Could not set the background', e); }
      }));
    if (h.background) {
      actions.append(hallButton('Remove background', async () => {
        try { await api('DELETE', `/api/halls/${h.id}/background`); await refreshHalls(); }
        catch (e) { toastError('Could not remove the background', e); }
      }));
    }
    actions.append(filePicker('Import seat blocks (CSV)…', '.csv,text/csv', async (input) => {
      const csv = await readFile(input, true);
      if (!csv) return;
      try {
        const res = await api('POST', `/api/halls/${h.id}/seat-blocks.csv`, { csv });
        toast(`Imported ${res.added} seat block(s)`, { type: 'success' });
        if (h.id === currentHall) { await loadSeatBlocks(); renderAll(); }
        await refreshHalls();
      } catch (e) {
        const lines = (e.body && e.body.errors || []).slice(0, 5)
          .map(x => (x.line ? `line ${x.line}: ` : '') + x.error).join('; ');
        toast(`Nothing was imported. ${lines || e.message}`, { type: 'error', duration: 12000 });
      }
    }));
    if (halls.length > 1) {
      actions.append(hallButton('Delete', async () => {
        const ok = await confirmDialog({ title: `Delete ${h.name}?`,
          text: 'Only an empty hall can be deleted: move or delete its switches and seat blocks first.' });
        if (!ok) return;
        try {
          await api('DELETE', `/api/halls/${h.id}`);
          if (h.id === currentHall) { goToHall(halls.find(x => x.id !== h.id).id); return; }
          await refreshHalls();
        } catch (e) { toastError('Could not delete the hall', e); }
      }, 'btn btn-danger btn-sm'));
    }
    row.append(name, info, actions);
    return row;
  }));
}

$('btn-halls').addEventListener('click', () => {
  renderHallsDialog();
  hallsBackdrop.classList.remove('hidden');
});
$('halls-close').addEventListener('click', () => hallsBackdrop.classList.add('hidden'));
hallsBackdrop.addEventListener('click', (e) => { if (e.target === hallsBackdrop) hallsBackdrop.classList.add('hidden'); });
$('halls-add').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('halls-add-name');
  try {
    const hall = await api('POST', '/api/halls', { name: input.value });
    input.value = '';
    await refreshHalls();
    toast(`Added ${hall.name}`, { type: 'success', action: { label: 'Open', onClick: () => goToHall(hall.id) } });
  } catch (err) { toastError('Could not add the hall', err); }
});
