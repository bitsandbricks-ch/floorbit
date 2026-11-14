'use strict';

// Settings > Backup and restore. Downloading is a plain link to GET /api/settings/backup.
// Restoring reads the chosen file, shows what it holds and asks once, then POSTs it.
// See docs/backup.md.

(() => {
  const fileInput = document.getElementById('st-restore-file');
  const confirmBox = document.getElementById('st-restore-confirm');
  const summary = document.getElementById('st-restore-summary');
  const goBtn = document.getElementById('st-restore-go');
  const cancelBtn = document.getElementById('st-restore-cancel');
  const result = document.getElementById('st-backup-result');
  if (!fileInput) return;

  let pending = null;

  function show(text, kind = '') {
    result.className = 'st-test-result' + (kind ? ' ' + kind : '');
    result.textContent = text;
  }

  function reset() {
    pending = null;
    fileInput.value = '';
    confirmBox.classList.add('hidden');
  }

  function plural(n, word, many = word + 's') { return `${n} ${n === 1 ? word : many}`; }

  fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    if (!file) return;
    show('');
    let backup;
    try {
      backup = JSON.parse(await file.text());
    } catch (_) {
      reset();
      show('✕ That file is not JSON. Pick a file made with "Download backup".', 'fail');
      return;
    }
    if (!backup || backup.format !== 'floorbit-backup') {
      reset();
      show('✕ That file is not a Floorbit backup.', 'fail');
      return;
    }
    const layout = backup.layout || {};
    const switchCount = (layout.switches || []).length + Object.keys(layout.positions || {}).length;
    const created = backup.created ? new Date(backup.created) : null;
    summary.textContent =
      `${file.name}` + (created && !isNaN(created) ? `, made ${created.toLocaleString()}` : '') +
      `: ${plural(switchCount, 'placed switch', 'placed switches')}, ${plural((layout.seat_blocks || []).length, 'seat block')}` +
      ` and ${plural(Object.keys(backup.settings || {}).length, 'saved setting')}.` +
      ' Restoring replaces the current floor plan and those settings for everyone.';
    pending = backup;
    confirmBox.classList.remove('hidden');
    goBtn.focus();
  });

  cancelBtn.addEventListener('click', () => { reset(); show(''); });

  goBtn.addEventListener('click', async () => {
    if (!pending) return;
    goBtn.disabled = true;
    show('Restoring…');
    try {
      const res = await fetch('/api/settings/backup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pending),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error || `Restore failed (${res.status})`);
      reset();
      const skipped = body.skipped_settings && body.skipped_settings.length
        ? ` Skipped ${plural(body.skipped_settings.length, 'setting')} this version doesn't know.` : '';
      show(`✓ Restored.${skipped} Reloading…`, 'ok');
      // Settings and the theme are rendered by the server, so reload to show them.
      setTimeout(() => location.reload(), 1200);
    } catch (e) {
      show('✕ ' + e.message, 'fail');
    } finally {
      goBtn.disabled = false;
    }
  });
})();
