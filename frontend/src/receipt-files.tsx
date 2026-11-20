import {FormEvent, useEffect, useState} from 'react';
import {Api, downloadReport, money, Transaction} from './api';

type Receipt = {
  id: number;
  original_name: string;
  media_type: string;
  bytes: number;
  uploaded_at: string;
  uploaded_by: string;
  replaces_id: number | null;
  replaced_by: number | null;
  replacement_reason: string | null;
};

const extensions: Record<string, string> = {'image/jpeg': 'jpg', 'image/png': 'png', 'application/pdf': 'pdf'};

async function encodeFile(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 8192) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  }
  return btoa(binary);
}

export function ReceiptFiles({api, transactions}: {api: Api; transactions: Transaction[]}) {
  const [purchase, setPurchase] = useState('');
  const [receipts, setReceipts] = useState<Receipt[] | null>(null);
  const [replacement, setReplacement] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [version, setVersion] = useState(0);
  const endpoint = '/transactions/' + purchase + '/files';

  useEffect(() => {
    if (!purchase) return;
    let active = true;
    api<Receipt[]>(endpoint).then(rows => {
      if (active) setReceipts(rows);
    }).catch((failure: Error) => {
      if (active) setError(failure.message);
    });
    return () => { active = false; };
  }, [api, endpoint, purchase, version]);

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const file = fields.get('receipt');
    if (!(file instanceof File) || !file.size || file.size > 5_000_000) {
      setError('Choose a PDF, JPEG or PNG receipt up to 5 MB.');
      return;
    }
    setError('');
    setStatus('');
    setBusy(true);
    try {
      await api(endpoint, 'POST', {
        name: file.name,
        content: await encodeFile(file),
        replaces_id: replacement ? Number(replacement) : null,
        reason: String(fields.get('reason') || ''),
      });
      form.reset();
      setReplacement('');
      setVersion(value => value + 1);
      setStatus(replacement ? 'Replacement uploaded. The previous file remains in history.' : 'Receipt attached.');
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function download(receipt: Receipt) {
    setError('');
    try {
      const name = receipt.original_name.replace(/\.[^.]+$/, '') + '.' + extensions[receipt.media_type];
      await downloadReport(api, endpoint + '/' + receipt.id, name);
    } catch (failure) {
      setError((failure as Error).message);
    }
  }

  return <section className="panel">
    <h2>Purchase receipts</h2>
    <label>Purchase for receipts<select value={purchase} disabled={busy} onChange={event => {
      setPurchase(event.target.value);
      setReplacement('');
      setReceipts(null);
      setError('');
      setStatus('');
    }}>
      <option value="">Select a purchase</option>
      {transactions.map(row => <option key={row.id} value={row.id}>
        #{row.id} · {row.purchase_date} · {row.supplier} · {money(row.cents)}{row.status === 'voided' ? ' · Voided' : ''}
      </option>)}
    </select></label>
    {purchase && receipts && <>
      <form key={purchase} onSubmit={add}>
        <label>Receipt file (PDF, JPEG or PNG, up to 5 MB)
          <input name="receipt" type="file" accept=".pdf,.jpg,.jpeg,.png" required/>
        </label>
        {receipts.some(row => !row.replaced_by) && <label>Receipt to replace (optional)
          <select value={replacement} onChange={event => setReplacement(event.target.value)} disabled={busy}>
            <option value="">Attach as a new receipt</option>
            {receipts.filter(row => !row.replaced_by).map(row => <option key={row.id} value={row.id}>
              #{row.id} · {row.original_name}
            </option>)}
          </select>
        </label>}
        {replacement && <label>Reason for replacing<input name="reason" required maxLength={1000}/></label>}
        <button disabled={busy}>{busy ? 'Uploading…' : replacement ? 'Upload replacement' : 'Attach receipt'}</button>
      </form>
      {receipts.length ? <div className="tablewrap"><table>
        <thead><tr><th>File</th><th>Upload</th><th>History</th><th>Action</th></tr></thead>
        <tbody>{receipts.map(row => <tr key={row.id}>
          <td>{row.original_name}<small>#{row.id} · {Math.ceil(row.bytes / 1024)} KB</small></td>
          <td>{new Date(row.uploaded_at).toLocaleString()}<small>{row.uploaded_by}</small></td>
          <td>{row.replaced_by ? 'Replaced by #' + row.replaced_by : 'Current'}
            {row.replaces_id && <small>Replaces #{row.replaces_id} · {row.replacement_reason}</small>}
          </td>
          <td><button className="secondary" onClick={() => download(row)} aria-label={'Download ' + row.original_name}>Download</button></td>
        </tr>)}</tbody>
      </table></div> : <p>No receipt files for this purchase.</p>}
    </>}
    {purchase && !receipts && !error && <p role="status">Loading receipt files…</p>}
    {status && <p role="status" className="success">{status}</p>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}
