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
          x: Math.max(0, Math.min(100, pendingCoords.x + (col - (cols - 1) / 2) * spacing)),
          y: Math.max(0, Math.min(100, pendingCoords.y + (row - (rowsCount - 1) / 2) * spacing)),
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
      setTool('select');
      renderAll();
      if (placed.length) {
        if (placed.length === 1) selectSwitch(placed[0].id);
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
      setTool('select');
      renderAll();
      selectSwitch(sw.id);
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

function blockModalValues() {
  return {
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
function updateBlockPreview() {
  const v = blockModalValues();
  const nums = blockSeatNumbers(v);
  const first = nums[0]?.number;
  const last = nums[nums.length - 1]?.number;
  blockPreview.textContent = `${nums.length} seat${nums.length === 1 ? '' : 's'}` +
    (first ? ` · numbered ${first}${nums.length > 1 ? ` to ${last}` : ''}` : '');
}
[blockName, blockCols, blockRows, blockRotation].forEach(el => el.addEventListener('input', updateBlockPreview));
blockReverseNumbersModal.addEventListener('change', updateBlockPreview);

function openBlockModal() {
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
    const block = await createBlock(data);
    const ref = { id: block.id };
    closeBlockModal();
    setTool('select');
    renderAll();
    selectBlock(block.id);
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
