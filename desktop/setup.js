const form = document.querySelector('form');
const message = document.querySelector('#error');
const button = document.querySelector('button');

function showError(error) {
  message.textContent = error;
  button.disabled = false;
}

window.asufcSetup.onPasswordError(showError);
form.addEventListener('submit', async event => {
  event.preventDefault();
  const fields = new FormData(form);
  const password = fields.get('password');
  if (password !== fields.get('confirmation')) {
    showError('The two passwords need to match.');
    return;
  }
  button.disabled = true;
  message.textContent = '';
  try {
    if (!await window.asufcSetup.setPassword(password)) showError('Could not set the password. Try again.');
  } catch {
    showError('Could not set the password. Close and reopen the app.');
  }
});
