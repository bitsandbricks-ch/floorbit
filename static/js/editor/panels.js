// Floor plan editor: the tool rail on the left and the panel on the right (search, layers,
// switches). A selection shows its inspector in the panel's place, so the plan keeps its width.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

const editPanel = $('edit-panel');
const PANELS = ['search', 'layers', 'switches'];
const PANEL_KEY = 'editorPanel';
// Phones get the panel as a drawer behind the ☰ button (touch.js); it starts closed there.
const panelNarrow = window.matchMedia('(max-width: 767.98px)');

let openPanelName = readJSON(PANEL_KEY, 'layers');   // null: closed
if (openPanelName !== null && !PANELS.includes(openPanelName)) openPanelName = 'layers';

// An inspector is open: the panel steps aside for it (style.css hides the panel then).
function inspectorOpen() {
  return !!document.querySelector('.main-layout > .detail-panel:not(.hidden)');
}

function syncPanel() {
  const shown = openPanelName !== null && !inspectorOpen();
  editPanel.classList.toggle('is-closed', openPanelName === null);
  for (const page of editPanel.querySelectorAll('.panel-page')) page.hidden = page.dataset.page !== openPanelName;
  for (const tab of editPanel.querySelectorAll('.panel-tab')) {
    tab.setAttribute('aria-selected', String(tab.dataset.panel === openPanelName));
    tab.tabIndex = tab.dataset.panel === openPanelName ? 0 : -1;
  }
  for (const btn of document.querySelectorAll('.rail-panel-btn')) {
    const on = shown && btn.dataset.panel === openPanelName;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-pressed', String(on));
  }
}

function openPanel(name, { focus = false } = {}) {
  if (inspectorOpen()) deselectAll();
  openPanelName = name;
  if (!panelNarrow.matches) writeJSON(PANEL_KEY, name);
  syncPanel();
  if (panelNarrow.matches && typeof setSidebarOpen === 'function') setSidebarOpen(true);
  if (focus && name === 'search') universalSearch.focus();
  else if (focus && name === 'switches') switchSearch.focus();
}

function closePanel() {
  openPanelName = null;
  if (!panelNarrow.matches) writeJSON(PANEL_KEY, null);
  syncPanel();
  if (panelNarrow.matches && typeof setSidebarOpen === 'function') setSidebarOpen(false);
}

// A rail button opens its panel, or closes it when it is already the one showing.
function togglePanel(name, opts) {
  if (openPanelName === name && !inspectorOpen() && !panelNarrow.matches) closePanel();
  else openPanel(name, opts);
}

for (const btn of document.querySelectorAll('.rail-panel-btn')) {
  btn.addEventListener('click', () => togglePanel(btn.dataset.panel, { focus: btn.dataset.panel === 'search' }));
}
for (const tab of editPanel.querySelectorAll('.panel-tab')) {
  // Arrow keys come from the shared tabs (static/js/ui/tabs.js).
  tab.addEventListener('click', () => openPanel(tab.dataset.panel));
}
$('btn-panel-close').addEventListener('click', closePanel);
// The ☰ drawer on phones (touch.js) always shows a page, even when the panel was closed on a computer.
$('btn-sidebar')?.addEventListener('click', () => { if (openPanelName === null) { openPanelName = 'layers'; syncPanel(); } });
// A status chip in the top bar filters the switch list, so show that list.
for (const chip of document.querySelectorAll('.status-chip')) {
  chip.addEventListener('click', () => { if (!panelNarrow.matches) openPanel('switches'); });
}

// The inspectors open and close all over the editor; follow them instead of hooking each one.
new MutationObserver(syncPanel).observe(document.querySelector('.main-layout'), {
  subtree: true, attributes: true, attributeFilter: ['class'],
});
syncPanel();

// ── German for the rail and the panel ────────────────────────────────────────────────
// The editor page has no translation layer yet; these are the texts of the menu, swapped in place
// when the language picked in the sidebar (or the browser's) is German. Swiss spelling ("ss").
const EDITOR_DE = {
  'Edit tools': 'Werkzeuge', 'Tools': 'Werkzeuge',
  'Select': 'Auswählen', 'Select and move': 'Auswählen und verschieben',
  'Select and move (V) · Shift+drag to select several': 'Auswählen und verschieben (V) · Shift+Ziehen wählt mehrere',
  'Switch': 'Switch', 'Add switch': 'Switch hinzufügen',
  'Add switch: click on the map to place it (S)': 'Switch hinzufügen: auf den Plan klicken, um ihn zu platzieren (S)',
  'Seat block': 'Platzblock', 'Add seat block': 'Platzblock hinzufügen',
  'Add seat block: click on the map to place it (B)': 'Platzblock hinzufügen: auf den Plan klicken, um ihn zu platzieren (B)',
  'Draw': 'Zeichnen', 'Add a label, wall, zone or icon (D)': 'Beschriftung, Wand, Zone oder Symbol hinzufügen (D)',
  'Text label': 'Beschriftung', 'Wall': 'Wand', 'Dashed line (fence, door)': 'Gestrichelte Linie (Zaun, Tür)',
  'Zone': 'Zone', 'Icon': 'Symbol',
  'Cable': 'Kabel', 'Draw a network or power cable (C)': 'Ein Netzwerk- oder Stromkabel zeichnen (C)',
  'Network cable (copper, fiber, DAC)': 'Netzwerkkabel (Kupfer, Glasfaser, DAC)', 'Power cable': 'Stromkabel',
  'Search': 'Suche', 'Search (/)': 'Suche (/)', 'Layers': 'Ebenen', 'Layers (L)': 'Ebenen (L)',
  'Switches': 'Switches', 'Switches (W)': 'Switches (W)', 'Panels': 'Bereiche',
  'Undo': 'Rückgängig', 'Undo (Ctrl+Z)': 'Rückgängig (Ctrl+Z)',
  'Redo': 'Wiederholen', 'Redo (Ctrl+Shift+Z)': 'Wiederholen (Ctrl+Shift+Z)',
  'Snap to grid': 'Am Raster ausrichten', 'Snap to grid (G)': 'Am Raster ausrichten (G)',
  'Keyboard shortcuts': 'Tastenkürzel', 'Keyboard shortcuts (?)': 'Tastenkürzel (?)',
  'Close the panel': 'Bereich schliessen',
  'Search, layers and switches': 'Suche, Ebenen und Switches',
  'Switch, seat, nick, IP or MAC…': 'Switch, Platz, Nick, IP oder MAC…',
  'Search switches, seats, nicks, IPs and MACs': 'Switches, Plätze, Nicks, IPs und MACs suchen',
  'Pick a result to select it on the plan.': 'Wähle ein Ergebnis, um es auf dem Plan auszuwählen.',
  'Grid': 'Raster', 'Grid that follows pan and zoom; the finest lines match the snap step': 'Raster, das Verschieben und Zoomen folgt; die feinsten Linien sind der Ausrichtungsschritt',
  'Seat states': 'Platzstatus', 'Draw seats online, offline or unknown, as on the Seats view': 'Plätze online, offline oder unbekannt zeichnen, wie in der Plätze-Ansicht',
  'Online': 'Online', 'Offline': 'Offline', 'Unknown': 'Unbekannt', 'Checked in': 'Eingecheckt',
  'Traffic heatmap': 'Verkehrs-Heatmap', 'Colour the map by throughput from LibreNMS': 'Den Plan nach Durchsatz aus LibreNMS einfärben',
  'Heatmap level': 'Heatmap-Ebene', 'Seats': 'Plätze', 'Both': 'Beides',
  "Each seat's switch port (download + upload)": 'Der Switch-Port jedes Platzes (Download + Upload)',
  'Total throughput of each switch': 'Gesamtdurchsatz jedes Switches', 'Seats and switches together': 'Plätze und Switches zusammen',
  'Seat port': 'Platz-Port', 'Switch total': 'Switch gesamt', 'No data or port down': 'Keine Daten oder Port down',
  'Power circuits': 'Stromkreise', 'Colour seats and switches by the load on their power circuit': 'Plätze und Switches nach der Last ihres Stromkreises einfärben',
  'Under the amber mark': 'Unter der gelben Marke', 'Getting close': 'Wird knapp',
  'About to trip, or tripped': 'Kurz vor dem Auslösen oder ausgelöst', 'No reading yet': 'Noch kein Messwert',
  'Always show switch labels': 'Switch-Namen immer zeigen', 'Always show switch names on the map': 'Switch-Namen immer auf dem Plan zeigen',
  'Labels, walls, zones, icons and cables': 'Beschriftungen, Wände, Zonen, Symbole und Kabel',
  'Overview': 'Übersicht', 'Labels, walls and zones for everyone': 'Beschriftungen, Wände und Zonen für alle',
  'Safety': 'Sicherheit', 'Exits, escape routes, extinguishers and the assembly point': 'Ausgänge, Fluchtwege, Feuerlöscher und der Sammelplatz',
  'Network': 'Netzwerk', 'Network gear and network cables drawn on the plan': 'Netzwerkgeräte und Netzwerkkabel, auf den Plan gezeichnet',
  'Electrical': 'Strom', 'Power sockets, boards and power cables drawn on the plan': 'Steckdosen, Verteiler und Stromkabel, auf den Plan gezeichnet',
  'Services': 'Dienste', 'Servers and services drawn on the plan': 'Server und Dienste, auf den Plan gezeichnet',
  'Open these layers on the Seats view': 'Diese Ebenen in der Plätze-Ansicht öffnen',
  'Sync devices': 'Geräte synchronisieren', 'Filter switches…': 'Switches filtern…', 'Filter switches': 'Switches filtern',
  'Clear status filter': 'Statusfilter entfernen', 'No switches placed yet.': 'Noch keine Switches platziert.',
};

function editorLang() {
  let lang = '';
  try { lang = localStorage.getItem('floorbit-lang') || ''; } catch { /* storage blocked */ }
  lang = lang || (navigator.languages || [navigator.language || 'en'])[0] || 'en';
  return lang.toLowerCase().startsWith('de') ? 'de' : 'en';
}

function translateMenu(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.nodeValue.trim();
    if (EDITOR_DE[text]) node.nodeValue = node.nodeValue.replace(text, EDITOR_DE[text]);
  }
  for (const el of root.querySelectorAll('[title], [aria-label], [placeholder]')) {
    for (const attr of ['title', 'aria-label', 'placeholder']) {
      const v = el.getAttribute(attr);
      if (v && EDITOR_DE[v]) el.setAttribute(attr, EDITOR_DE[v]);
    }
  }
  if (root.getAttribute('aria-label') && EDITOR_DE[root.getAttribute('aria-label')]) {
    root.setAttribute('aria-label', EDITOR_DE[root.getAttribute('aria-label')]);
  }
}

if (editorLang() === 'de') {
  [$('tool-rail'), editPanel, $('btn-sidebar')].forEach(el => el && translateMenu(el));
}
