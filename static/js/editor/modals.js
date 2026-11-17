// Floor plan editor: The add-switch and seat-block dialogs.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// ── Add-switch modal ─────────────────────────────────────────────────────────────────
let activeModalTab = 'manual'; // 'netbox' | 'manual'
let isMultiselectMode = false;

function openAddModal() {
  pendingPickerDeviceId = null;
  selectedDeviceIds.clear();
  isMultiselectMode = false;
  multiselectToggle.checked = false;
  updateMultiselectCount();

  if (config.netbox_enabled) {
    modalTabs.classList.remove('hidden');
    const unplaced = switches.filter(s => !s.placed && s.source !== 'manual');
    setModalTab(unplaced.length > 0 ? 'netbox' : 'manual');
  } else {
    modalTabs.classList.add('hidden');
    setModalTab('manual');
  }

  let n = switches.filter(s => s.source === 'manual').length + 1;
  let def = `SW-${String(n).padStart(2, '0')}`;
  const names = switches.map(s => s.name);
  while (names.includes(def)) { n++; def = `SW-${String(n).padStart(2, '0')}`; }
  switchNameInput.value = def;

  modalBackdrop.classList.remove('hidden');

  if (activeModalTab === 'netbox') {
    deviceFilter.value = '';
    renderDevicePicker('');
    deviceFilter.focus();
  } else {
    switchNameInput.focus();
    switchNameInput.select();
  }
}

function setModalTab(tab) {
  activeModalTab = tab;
  tabNetbox.classList.toggle('active', tab === 'netbox');
  tabManual.classList.toggle('active', tab === 'manual');
  modalNetbox.classList.toggle('hidden', tab !== 'netbox');
  modalManual.classList.toggle('hidden', tab !== 'manual');
}

tabNetbox.addEventListener('click', () => {
  setModalTab('netbox');
  deviceFilter.value = '';
  renderDevicePicker('');
  deviceFilter.focus();
});
tabManual.addEventListener('click', () => {
  setModalTab('manual');
  switchNameInput.focus();
  switchNameInput.select();
});

function renderDevicePicker(filter) {
  const unplaced = switches.filter(s =>
    !s.placed && s.source !== 'manual' && s.name.toLowerCase().includes(filter.toLowerCase()));
  if (!unplaced.length) {
    deviceList.innerHTML = `<div class="device-empty">No devices left to place${filter ? ' matching the filter' : ''}</div>`;
    return;
  }
  deviceList.innerHTML = '';
  for (const dev of unplaced) {
    const item = document.createElement('div');
    const isSelected = selectedDeviceIds.has(dev.id);
    item.className = 'device-item' + (isMultiselectMode ? ' multiselect-mode' : '') +
      (dev.id === pendingPickerDeviceId || isSelected ? ' selected' : '');
    item.dataset.id = dev.id;
    item.innerHTML = `
      ${isMultiselectMode ? `<span class="device-item-checkbox ${isSelected ? 'checked' : ''}"></span>` : ''}
      <span class="device-item-name">${escHtml(dev.name)}</span>
      <span class="device-item-badge">${escHtml(dev.netbox_status || '')}</span>`;
    item.addEventListener('click', () => {
      if (isMultiselectMode) {
        if (selectedDeviceIds.has(dev.id)) selectedDeviceIds.delete(dev.id);
        else selectedDeviceIds.add(dev.id);
        updateMultiselectCount();
        renderDevicePicker(filter);
      } else {
        pendingPickerDeviceId = dev.id;
        for (const el of deviceList.querySelectorAll('.device-item'))
          el.classList.toggle('selected', el.dataset.id === dev.id);
      }
    });
    item.addEventListener('dblclick', () => { if (!isMultiselectMode) modalConfirm.click(); });
    deviceList.appendChild(item);
  }
}

function updateMultiselectCount() {
  const count = selectedDeviceIds.size;
  multiselectCount.textContent = `${count} selected`;
  multiselectCount.style.display = count > 0 ? 'block' : 'none';
}

deviceFilter.addEventListener('input', () => renderDevicePicker(deviceFilter.value));
deviceFilter.addEventListener('keydown', (e) => {
  if (e.key === 'Enter')  modalConfirm.click();
  if (e.key === 'Escape') closeAddModal();
});

multiselectToggle.addEventListener('change', () => {
  isMultiselectMode = multiselectToggle.checked;
  if (isMultiselectMode) {
    if (pendingPickerDeviceId) { selectedDeviceIds.add(pendingPickerDeviceId); pendingPickerDeviceId = null; }
  } else {
    selectedDeviceIds.clear();
  }
  updateMultiselectCount();
  renderDevicePicker(deviceFilter.value);
});

function closeAddModal() {
  modalBackdrop.classList.add('hidden');
  pendingCoords = null;
  pendingPickerDeviceId = null;
  selectedDeviceIds.clear();
  isMultiselectMode = false;
}

modalCancel.addEventListener('click', closeAddModal);
modalBackdrop.addEventListener('click', (e) => { if (e.target === modalBackdrop) closeAddModal(); });
switchNameInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter')  modalConfirm.click();
  if (e.key === 'Escape') closeAddModal();
});

modalConfirm.addEventListener('click', async () => {
  if (!pendingCoords) return;
  modalConfirm.disabled = true;
  try {
    if (activeModalTab === 'netbox' && config.netbox_enabled) {
      const ids = isMultiselectMode ? Array.from(selectedDeviceIds)
                                    : (pendingPickerDeviceId ? [pendingPickerDeviceId] : []);
      if (!ids.length) { deviceFilter.focus(); return; }

      // Place several devices in a grid around the click point
      const cols = Math.ceil(Math.sqrt(ids.length));
      const rowsCount = Math.ceil(ids.length / cols);
      const spacing = 8; // % of the floor plan
      const placements = ids.map((id, i) => {
        const row = Math.floor(i / cols);
        const col = i % cols;
        return {
          id,
          x: pendingCoords.x + (col - (cols - 1) / 2) * spacing,
          y: pendingCoords.y + (row - (rowsCount - 1) / 2) * spacing,
        };
      });

      const placed = [];
      for (const p of placements) {
        try {
          await updateSwitch(p.id, { x: p.x, y: p.y });
          placed.push(p);
        } catch (e) {
          const name = switches.find(s => s.id === p.id)?.name || p.id;
          toastError(`Could not place ${name}`, e);
        }
      }
      closeAddModal();
      renderAll();   // the tool stays: place the next one (Esc or V to stop)
      if (placed.length) {
        pushHistory({
          label: placed.length === 1 ? 'place switch' : `place ${placed.length} switches`,
          undo: async () => { for (const p of placed) await deleteSwitch(resolveId(p.id)); },
          redo: async () => { for (const p of placed) await updateSwitch(resolveId(p.id), { x: p.x, y: p.y }); },
        });
      }
    } else {
      const name = switchNameInput.value.trim();
      if (!name) { switchNameInput.focus(); return; }
      const data = { name, ...pendingCoords };
      const sw = await createManualSwitch(data);
      const ref = { id: sw.id };
      closeAddModal();
      renderAll();
      pushHistory({
        label: `add ${name}`,
        undo: () => deleteSwitch(resolveId(ref.id)),
        redo: async () => {
          const created = await createManualSwitch(data);
          aliasId(resolveId(ref.id), created.id);
          ref.id = created.id;
        },
      });
    }
  } catch (e) {
    toastError('Could not place switch', e);
  } finally {
    modalConfirm.disabled = false;
  }
});
// ── Seat block modal ─────────────────────────────────────────────────────────────────
const blockBackdrop    = $('block-backdrop');
const blockName        = $('block-name');
const blockCols        = $('block-cols');
const blockRows        = $('block-rows');
const blockSpacingX    = $('block-spacing-x');
const blockSpacingY    = $('block-spacing-y');
const blockRotation    = $('block-rotation');
const blockReverseNumbersModal = $('block-reverse-numbers-modal');
const blockCancel      = $('block-cancel');
const blockConfirm     = $('block-confirm');
const blockPreview     = $('block-preview');
const blockNaming      = $('block-naming');
const blockRowStart    = $('block-row-start');
const blockRowLabels   = $('block-row-labels');
const blockCount       = $('block-count');
const blockDirection   = $('block-direction');
const blockGap         = $('block-gap');

// The first row letter no block uses yet, so a new block carries on the rows. Seat names count
// over every hall, and seatBlocks has only the shown one's, so ask the server for all of them.
let allSeatRows = [];
async function loadAllSeatRows() {
  try {
    allSeatRows = (await api('GET', '/api/seat-blocks')).map(b => b.seat_rows || []);
  } catch (_) { allSeatRows = []; }
}
function nextFreeRow() {
  let next = 0;
  const names = [...allSeatRows.flat(2), ...seatBlocks.flatMap(b => blockSeatNumbers(b).map(n => n.number))];
  for (const number of names) {
    const prefix = String(number).split('-')[0];
    if (/^[A-Z]{1,2}$/i.test(prefix)) next = Math.max(next, letterIndex(prefix) + 1);
  }
  return rowLetter(next);
}

// How far apart (in % of the plan) to put the copies: the block's size on screen plus the gap.
function blockStep(v) {
  const box = blocksOverlay.getBoundingClientRect();
  const labelled = v.naming === 'rows' && v.row_labels !== 'none';
  const extraCols = labelled ? (v.row_labels === 'both' ? 2 : 1) : 0;
  let w = (v.cols + extraCols) * 20 + 10;
  let h = v.rows * 20 + 10 + (v.name ? 14 : 0);
  if ([1, 3].includes(blockQuarter(v))) [w, h] = [h, w];
  const gap = Math.max(0, parseFloat(blockGap.value) || 0);
  return blockDirection.value === 'right'
    ? { dx: (box.width ? (w / box.width) * 100 : 10) + gap, dy: 0 }
    : { dx: 0, dy: (box.height ? (h / box.height) * 100 : 10) + gap };
}

function blockModalValues() {
  return {
    naming: blockNaming.value,
    row_start: (blockRowStart.value.trim() || 'A').toUpperCase(),
    row_labels: blockRowLabels.value,
    name: blockName.value.trim(),
    cols: Math.max(1, parseInt(blockCols.value) || 1),
    rows: Math.max(1, parseInt(blockRows.value) || 1),
    seat_width: 1.5,
    seat_height: 1.5,
    spacing_x: parseFloat(blockSpacingX.value) || 0.5,
    spacing_y: parseFloat(blockSpacingY.value) || 1,
    numbering_pattern: 'blockname_number',
    reverse_numbers: blockReverseNumbersModal.checked,
    rotation: parseInt(blockRotation.value) || 0,
  };
}
function blockCopies() { return Math.min(30, Math.max(1, parseInt(blockCount.value) || 1)); }

function updateBlockPreview() {
  const v = blockModalValues();
  const rows = v.naming === 'rows';
  $('block-row-start-field').classList.toggle('hidden', !rows);
  $('block-row-labels-field').classList.toggle('hidden', !rows);
  $('block-name-hint').textContent = rows ? '(optional, shown above the block)' : '(optional, used as seat prefix: A-1, A-2…)';
  const many = blockCopies() > 1;
  $('block-direction-field').classList.toggle('hidden', !many);
  $('block-gap-field').classList.toggle('hidden', !many);
  const n = blockCopies();
  const seats = v.cols * v.rows * n;
  let text = `${n > 1 ? `${n} blocks · ` : ''}${seats} seat${seats === 1 ? '' : 's'}`;
  if (rows) {
    const first = letterIndex(v.row_start);
    const total = v.rows * n;
    text += total > 1 ? ` · rows ${rowLetter(first)} to ${rowLetter(first + total - 1)}` : ` · row ${rowLetter(first)}`;
    text += `, each numbered 1 to ${v.cols}`;
  } else {
    const nums = blockSeatNumbers(v);
    const firstNum = nums[0]?.number;
    if (firstNum) text += ` · numbered ${firstNum}${nums.length > 1 ? ` to ${nums[nums.length - 1].number}` : ''}`;
  }
  blockPreview.textContent = text;
}
[blockName, blockCols, blockRows, blockRotation, blockRowStart, blockCount, blockGap].forEach(el => el.addEventListener('input', updateBlockPreview));
[blockReverseNumbersModal, blockNaming, blockRowLabels, blockDirection].forEach(el => el.addEventListener('change', updateBlockPreview));

async function openBlockModal() {
  await loadAllSeatRows();
  blockNaming.value = 'rows';
  blockRowStart.value = nextFreeRow();
  blockRowLabels.value = 'start';
  blockCount.value = '1';
  blockDirection.value = 'down';
  blockGap.value = '3';
  blockName.value = '';
  blockCols.value = '8';
  blockRows.value = '1';
  blockSpacingX.value = '0.5';
  blockSpacingY.value = '1';
  blockRotation.value = '0';
  blockReverseNumbersModal.checked = false;
  updateBlockPreview();
  blockBackdrop.classList.remove('hidden');
  blockName.focus();
}

function closeBlockModal() {
  blockBackdrop.classList.add('hidden');
  pendingCoords = null;
}

blockCancel.addEventListener('click', closeBlockModal);
blockBackdrop.addEventListener('click', (e) => { if (e.target === blockBackdrop) closeBlockModal(); });
blockBackdrop.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type !== 'checkbox') blockConfirm.click();
});
blockConfirm.addEventListener('click', async () => {
  if (!pendingCoords) return;
  blockConfirm.disabled = true;
  try {
    const data = { ...blockModalValues(), ...pendingCoords };
    if (blockCopies() > 1) {
      const many = { ...data, count: blockCopies(), ...blockStep(data) };
      let made = await createBlocks(many);
      closeBlockModal();
      renderAll();
      toast(`${made.length} seat blocks added`, { type: 'success', duration: 2500 });
      pushHistory({
        label: `add ${made.length} seat blocks`,
        undo: async () => { for (const b of made) await deleteBlock(resolveId(b.id)); },
        redo: async () => {
          const again = await createBlocks(many);
          made.forEach((b, i) => aliasId(resolveId(b.id), again[i].id));
          made = again;
        },
      });
      return;
    }
    const block = await createBlock(data);
    const ref = { id: block.id };
    closeBlockModal();
    renderAll();
    pushHistory({
      label: `add ${data.name || 'seat block'}`,
      undo: () => deleteBlock(resolveId(ref.id)),
      redo: async () => {
        const created = await createBlock(data);
        aliasId(resolveId(ref.id), created.id);
        ref.id = created.id;
      },
    });
  } catch (e) {
    toastError('Could not create seat block', e);
  } finally {
    blockConfirm.disabled = false;
  }
});
