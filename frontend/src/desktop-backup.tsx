import {FormEvent, useState} from 'react';
import {Api} from './api';

type DesktopWindow = Window & {
  asufcDesktop?: boolean;
  asufcRecovery?: {
    chooseBackup: () => Promise<string>;
    restoreBackup: (passphrase: string) => Promise<{ok: boolean; message?: string}>;
  };
};
export const desktop = (window as DesktopWindow).asufcDesktop === true;
const recovery = (window as DesktopWindow).asufcRecovery;

function DesktopRestore() {
  const [file, setFile] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function choose() {
    if (!recovery || busy) return;
    setError('');
    setBusy(true);
    setFile('');
    try {
      setFile(await recovery.chooseBackup());
    } catch {
      setError('Could not open the file picker. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function restore(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const passphrase = new FormData(event.currentTarget).get('restore_passphrase');
    if (!recovery || !file || busy || typeof passphrase !== 'string') return;
    setError('');
    setBusy(true);
    try {
      const result = await recovery.restoreBackup(passphrase);
      if (!result.ok) throw new Error(result.message || 'Could not restore the backup.');
      window.location.reload();
    } catch (failure) {
      setError((failure as Error).message);
      setBusy(false);
    }
  }

  return <section className="panel">
    <h2>Restore an encrypted backup</h2>
    <p>Restore into an empty ledger. To recover alongside an existing ledger, use a fresh operating-system profile.</p>
    <button type="button" onClick={choose} disabled={busy}>Choose backup file</button>
    <p aria-live="polite">{file || 'No backup selected'}</p>
    <form onSubmit={restore}>
      <label>Passphrase from the selected backup<input name="restore_passphrase" type="password"
        required minLength={16} maxLength={1024} autoComplete="off"/></label>
      <button disabled={busy || !file}>{busy ? 'Please wait…' : 'Restore backup'}</button>
    </form>
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

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

  return <><section className="panel">
    <h2>Encrypted ledger backup</h2>
    <p>Save a copy of the ledger, receipts and audit history. Use a backup passphrase of at least 16 characters and keep it in a safe place.</p>
    <form onSubmit={backup}>
      <label>Backup passphrase<input name="passphrase" type="password" required minLength={16} maxLength={1024} autoComplete="off"/></label>
      <label>Confirm backup passphrase<input name="confirmation" type="password" required minLength={16} maxLength={1024} autoComplete="off"/></label>
      <button disabled={busy}>{busy ? 'Preparing backup…' : 'Save encrypted backup'}</button>
    </form>
    {error && <p role="alert" className="error">{error}</p>}
    {message && <p role="status">{message}</p>}
  </section>{recovery && <DesktopRestore/>}</>;
}
