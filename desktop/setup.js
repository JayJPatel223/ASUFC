const newLedger = document.querySelector('#new-ledger');
const restoreLedger = document.querySelector('#restore-ledger');
const feedback = document.querySelector('#error');
const createButton = newLedger.querySelector('button[type=submit]');
const chooseButton = document.querySelector('#choose-backup');
const restoreButton = document.querySelector('#restore-backup');
const selectedLabel = document.querySelector('#selected-backup');
let selectedBackup = '';

function busy(pending) {
  createButton.disabled = pending;
  chooseButton.disabled = pending;
  restoreButton.disabled = pending || !selectedBackup;
}

function showError(message) {
  feedback.textContent = message;
  selectedLabel.textContent = selectedBackup || 'No backup selected';
  busy(false);
}

window.asufcSetup.onPasswordError(showError);
newLedger.addEventListener('submit', async event => {
  event.preventDefault();
  const fields = new FormData(newLedger);
  const password = fields.get('password');
  if (password !== fields.get('confirmation')) {
    showError('The two passwords need to match.');
    return;
  }
  busy(true);
  feedback.textContent = '';
  try {
    if (!await window.asufcSetup.setPassword(password)) showError('Could not set the password. Try again.');
  } catch {
    showError('Could not set the password. Close and reopen the app.');
  }
});

chooseButton.addEventListener('click', async () => {
  busy(true);
  feedback.textContent = '';
  try {
    selectedBackup = await window.asufcSetup.chooseBackup();
    selectedLabel.textContent = selectedBackup || 'No backup selected';
    busy(false);
  } catch {
    showError('Could not open the file picker. Try again.');
  }
});

restoreLedger.addEventListener('submit', async event => {
  event.preventDefault();
  busy(true);
  feedback.textContent = '';
  selectedLabel.textContent = 'Restoring ' + selectedBackup + '…';
  try {
    const passphrase = new FormData(restoreLedger).get('passphrase');
    if (!await window.asufcSetup.restoreBackup(passphrase)) showError('Could not start the restore. Choose a backup and try again.');
  } catch {
    showError('The restore could not start. Close and reopen the app.');
  }
});
