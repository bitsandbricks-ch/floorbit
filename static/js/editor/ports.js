// Floor plan editor: port actions on the selected seat (issue #16) and "Flag for a tech".
// Bounce asks the server, which resolves the seat to its switch port itself; the browser never
// names a switch or port. The switch login is typed for each action and never kept here either.
// Classic script sharing one global scope with the other editor/*.js files (see README.md).
'use strict';

const portActionsOn = document.body.dataset.portActions === 'on';
let portInfo = null;          // {available, needs_login, plugin} from /api/ports
let portDialogMode = null;    // 'bounce' or 'flag'
let portDialogSeat = null;

const portBackdrop = $('port-backdrop');
const portForm = $('port-form');
const portTitle = $('port-title');
const portText = $('port-text');
const portLogin = $('port-login');
const portUsername = $('port-username');
const portPassword = $('port-password');
const portNoteField = $('port-note-field');
const portNote = $('port-note');
const portError = $('port-error');
const portOk = $('port-ok');
const seatPortBounce = $('seat-port-bounce');
const seatFlag = $('seat-flag');

async function loadPortInfo() {
  if (portActionsOn) {
    try {
      portInfo = await api('GET', '/api/ports');
    } catch {
      portInfo = null;   // port actions are extra; the floor plan works without them
    }
  }
  seatPortBounce.classList.toggle('hidden', !portInfo?.available);
  seatFlag.classList.toggle('hidden', document.body.dataset.incidents !== 'on');
}

function portDialogOpen() { return !portBackdrop.classList.contains('hidden'); }

function closePortDialog() {
  portBackdrop.classList.add('hidden');
  portPassword.value = '';      // never left in the page after the dialog closes
  portDialogMode = null;
}

let portMatchZone = null;   // set once the server said the seat is a match seat (issue #31)

function openPortDialog(mode, seat) {
  portMatchZone = null;
  portDialogMode = mode;
  portDialogSeat = seat;
  portError.classList.add('hidden');
  portNote.value = '';
  portPassword.value = '';
  const bounce = mode === 'bounce';
  portTitle.textContent = bounce ? `Bounce the port of seat ${seat}` : `Flag seat ${seat} for a tech`;
  portText.textContent = bounce
    ? 'The switch port goes down for a few seconds and comes back up. The player loses their connection meanwhile.'
    : 'Files an incident for this seat. It shows on the incident board and as a red ring on the floor plan.';
  portLogin.classList.toggle('hidden', !(bounce && portInfo?.needs_login));
  portNoteField.classList.toggle('hidden', bounce);
  portOk.textContent = bounce ? 'Bounce port' : 'Flag seat';
  portOk.className = bounce ? 'btn btn-danger-solid' : 'btn btn-primary';
  portBackdrop.classList.remove('hidden');
  (bounce ? (portInfo?.needs_login ? (portUsername.value ? portPassword : portUsername) : portOk) : portNote).focus();
}

portForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const seat = portDialogSeat;
  portOk.disabled = true;
  portError.classList.add('hidden');
  try {
    if (portDialogMode === 'bounce') {
      const body = { seat };
      if (portMatchZone) body.confirm_match = true;
      if (portInfo?.needs_login) Object.assign(body, { username: portUsername.value.trim(), password: portPassword.value });
      portPassword.value = '';
      const result = await api('POST', '/api/ports/bounce', body);
      closePortDialog();
      toast(result.message, { type: 'success' });
      setTimeout(() => {
        if (selectedType === 'seat' && currentBlockSeatNumber === seat) lookupSeatPort(seat).catch(() => {});
      }, 2000);
    } else {
      await api('POST', '/api/incidents', { seat, title: 'Tech visit', note: portNote.value });
      closePortDialog();
      toast(`Seat ${seat} is flagged for a tech.`, { type: 'success' });
      loadIncidentMarkers();
    }
  } catch (err) {
    if (err.body && err.body.match_seat && !portMatchZone) {
      // A tournament seat: say so and make the next click the second confirmation.
      portMatchZone = err.body.match_seat;
      portOk.textContent = 'Bounce the match seat anyway';
    }
    portError.textContent = err.message;
    portError.classList.remove('hidden');
  } finally {
    portOk.disabled = false;
  }
});
$('port-cancel').addEventListener('click', closePortDialog);
portBackdrop.addEventListener('click', (e) => { if (e.target === portBackdrop) closePortDialog(); });
seatPortBounce.addEventListener('click', () => {
  if (selectedType === 'seat' && currentBlockSeatNumber) openPortDialog('bounce', currentBlockSeatNumber);
});
seatFlag.addEventListener('click', () => {
  if (selectedType === 'seat' && currentBlockSeatNumber) openPortDialog('flag', currentBlockSeatNumber);
});
