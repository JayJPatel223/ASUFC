import {useState} from 'react';
import {Api, money} from './api';

export type PendingPurchase = {
  id: number;
  program_code: string;
  purchase_date: string;
  supplier: string;
  purchase_type: string;
  description: string;
  cents: number;
  notes: string;
  verify_charge: boolean;
};

type StarterFunding = {
  name: string;
  kind: 'cash' | 'credit';
  expected_cents: number;
  received_cents: number;
  expiry?: string;
  carry_status?: string;
};
type Starter = {
  version: number;
  period: {academic_year: string; starts_on: string; ends_on: string};
  semesters: {name: string; starts_on: string; ends_on: string}[];
  funding: StarterFunding[];
  purchases: Omit<PendingPurchase, 'id'>[];
};

export function StaffSetup({api, onApplied}: {api: Api; onApplied: (message: string) => void}) {
  const [starter, setStarter] = useState<Starter | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function read(file: File | undefined) {
    setStarter(null);
    setError('');
    if (!file) return;
    try {
      if (file.size > 500_000) throw new Error();
      const data = JSON.parse(await file.text());
      if (data?.version !== 1 || typeof data.period?.academic_year !== 'string' ||
          !Array.isArray(data.semesters) || !Array.isArray(data.funding) || !Array.isArray(data.purchases) ||
          data.funding.some((row: StarterFunding) => typeof row?.name !== 'string' ||
            !Number.isSafeInteger(row.received_cents) || !Number.isSafeInteger(row.expected_cents)) ||
          data.purchases.some((row: PendingPurchase) => !Number.isSafeInteger(row?.cents)) ||
          data.semesters.some((row: Starter['semesters'][number]) => typeof row?.name !== 'string')) {
        throw new Error();
      }
      setStarter(data);
    } catch {
      setError('Choose a valid ASUFC starter file under 500 KB.');
    }
  }

  async function apply() {
    if (!starter || !window.confirm('Apply these funding and reporting settings and add the purchases to Pending purchases?')) return;
    setError('');
    setBusy(true);
    try {
      const result = await api<{funding_sources: number; pending_purchases: number}>('/staff-setup', 'POST', starter);
      setStarter(null);
      onApplied(`Applied ${result.funding_sources} funding sources and staged ${result.pending_purchases} purchases for review.`);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="panel">
    <h2>Set up a new ledger from a starter file</h2>
    <p>A starter file adds funding sources, reporting dates and purchases awaiting review. Pending purchases leave funding balances unchanged until someone confirms them.</p>
    <label>ASUFC starter file<input type="file" accept=".json" disabled={busy} onChange={event => read(event.target.files?.[0])}/></label>
    {starter && <>
      <h3>Reporting year {starter.period.academic_year}</h3>
      <p>Check the reporting range. It is editable here and in Academic years after setup.</p>
      <div className="twocol">
        <label>Reporting start<input type="date" value={starter.period.starts_on} onChange={event => {
          const date = event.target.value;
          setStarter(value => value && ({...value, period: {...value.period, starts_on: date}}));
        }}/></label>
        <label>Reporting end<input type="date" value={starter.period.ends_on} onChange={event => {
          const date = event.target.value;
          setStarter(value => value && ({...value, period: {...value.period, ends_on: date}}));
        }}/></label>
      </div>
      <ul>{starter.semesters.map((term, i) => <li key={i}>{term.name} · {term.starts_on} to {term.ends_on}</li>)}</ul>
      <div className="tablewrap"><table>
        <thead><tr><th>Funding source</th><th>Award</th><th>Received</th><th>Expiry</th><th>Carry-forward</th></tr></thead>
        <tbody>{starter.funding.map((grant, i) => <tr key={i}>
          <th scope="row">{grant.name}<small>{grant.kind === 'credit' ? 'Purchasing credit' : 'Cash'}</small></th>
          <td>{money(grant.expected_cents)}</td><td>{money(grant.received_cents)}</td><td>{grant.expiry || '—'}</td>
          <td>{grant.carry_status === 'prohibited' ? 'Prohibited' : grant.carry_status === 'allowed' ? 'Allowed' : 'To confirm'}</td>
        </tr>)}</tbody>
      </table></div>
      <p>{starter.purchases.length} pending purchases · {money(starter.purchases.reduce((sum, row) => sum + row.cents, 0))} recorded in the source file</p>
      <button disabled={busy || !starter.period.starts_on || !starter.period.ends_on} onClick={apply}>
        {busy ? 'Applying…' : 'Apply starter file'}
      </button>
    </>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}
