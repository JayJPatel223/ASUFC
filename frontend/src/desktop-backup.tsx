import {FormEvent, useState} from 'react';
import {Api} from './api';

export const desktop = (window as Window & {asufcDesktop?: boolean}).asufcDesktop === true;

export function DesktopBackup({api}: {api: Api}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function backup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const passphrase = fields.get('passphrase');
    setMessage('');
    setError('');
    if (passphrase !== fields.get('confirmation')) {
      setError('The two backup passphrases need to match.');
      return;
    }
    setBusy(true);
    try {
      const {key} = await api<{key: string}>('/desktop/backup', 'POST', {passphrase});
      const link = document.createElement('a');
      link.href = '/api/desktop/backup/' + encodeURIComponent(key);
      link.download = '';
      link.click();
      form.reset();
      setMessage('Choose where to save the encrypted backup, then check that the file appears there.');
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="panel">
    <h2>Encrypted ledger backup</h2>
    <p>Save a copy of the ledger, receipts and audit history. Use a separate backup passphrase of at least 16 characters and keep it in a safe place.</p>
    <form onSubmit={backup}>
      <label>Backup passphrase<input name="passphrase" type="password" required minLength={16} maxLength={1024} autoComplete="off"/></label>
      <label>Confirm backup passphrase<input name="confirmation" type="password" required minLength={16} maxLength={1024} autoComplete="off"/></label>
      <button disabled={busy}>{busy ? 'Preparing backup…' : 'Save encrypted backup'}</button>
    </form>
    {error && <p role="alert" className="error">{error}</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
