import {useEffect, useState} from 'react';
import {Api, money, Program} from './api';

type Kind = 'cash' | 'credit';
type Spend = {label: string; cash_cents: number; credit_cents: number};
type ProgramSpend = {kind: Kind; code: string; allocated_cents: number; spent_cents: number};
type FundingInsight = {
  id: number;
  name: string;
  kind: Kind;
  expiry: string | null;
  remaining_cents: number;
  unreceived_cents: number;
  days_to_expiry: number | null;
  low_balance: boolean;
};
type Insights = {
  spending: {totals: Spend; purchase_count: number; month: Spend[]};
  previous_month: Spend;
  balances: Record<Kind, {budget_remaining_cents: number; funding_remaining_cents: number}>;
  programs: ProgramSpend[];
  funding: FundingInsight[];
  forecast: {status: string; estimate: Spend | null; months: string[]};
};
const kinds = ['cash', 'credit'] as const;
const labels = {cash: 'Cash', credit: 'Purchasing credits'};
const amount = (row: Spend, kind: Kind) => kind === 'cash' ? row.cash_cents : row.credit_cents;

export function FinancialInsights({api, year, programs}: {api: Api; year: string; programs: Program[]}) {
  const [program, setProgram] = useState('');
  const [result, setResult] = useState<Insights | null>(null);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    setResult(null);
    setError('');
    const query = new URLSearchParams({year});
    if (program) query.set('program', program);
    api<Insights>('/reports/financial-insights?' + query).then(data => {
      if (active) setResult(data);
    }).catch((failure: Error) => {
      if (active) setError(failure.message);
    });
    return () => { active = false; };
  }, [api, program, version, year]);

  return <>
    <section className="panel">
      <h2>Ledger summary</h2>
      <label>Program for insights<select value={program} onChange={event => setProgram(event.target.value)}>
        <option value="">All programs</option>
        {programs.map(row => <option key={row.code} value={row.code}>{row.name}</option>)}
      </select></label>
      {error && <p role="alert" className="error">{error} <button onClick={() => setVersion(value => value + 1)}>Retry</button></p>}
      {!error && !result && <p role="status">Calculating ledger totals…</p>}
      {result && <>
        <p>{result.spending.purchase_count} confirmed {result.spending.purchase_count === 1 ? 'purchase' : 'purchases'} in {year}.</p>
        <div className="tablewrap"><table>
          <thead><tr><th>Payment</th><th>Year spending</th><th>Last month ({result.previous_month.label})</th>
            <th>Allocated budget left</th>{!program && <th>Funding balance left</th>}</tr></thead>
          <tbody>{kinds.map(kind => <tr key={kind}><th scope="row">{labels[kind]}</th>
            <td>{money(amount(result.spending.totals, kind))}</td>
            <td>{money(amount(result.previous_month, kind))}</td>
            <td>{money(result.balances[kind].budget_remaining_cents)}</td>
            {!program && <td>{money(result.balances[kind].funding_remaining_cents)}</td>}
          </tr>)}</tbody>
        </table></div>
      </>}
    </section>
    {result && <>
      <section className="panel">
        <h2>Monthly spending</h2>
        <MonthlySpending months={result.spending.month}/>
      </section>
      <section className="panel">
        <h2>Program budget use</h2>
        {result.programs.length ? <div className="tablewrap"><table>
          <thead><tr><th>Program</th><th>Payment</th><th>Allocated</th><th>Spent</th><th>Left</th><th>Used</th></tr></thead>
          <tbody>{[...result.programs].sort((a, b) => a.kind.localeCompare(b.kind) || b.spent_cents - a.spent_cents).map(row => {
            const percent = row.allocated_cents ? Math.round(row.spent_cents * 100 / row.allocated_cents) : 0;
            return <tr key={row.code + row.kind}>
              <th scope="row">{programs.find(item => item.code === row.code)?.name || row.code}</th>
              <td>{labels[row.kind]}</td><td>{money(row.allocated_cents)}</td><td>{money(row.spent_cents)}</td>
              <td>{money(row.allocated_cents - row.spent_cents)}</td><td>{percent}%</td>
            </tr>;
          })}</tbody>
        </table></div> : <p>No budgets in this selection.</p>}
      </section>
      {!program && <section className="panel">
        <h2>Funding balances and alerts</h2>
        {result.funding.length ? <div className="tablewrap"><table>
          <thead><tr><th>Source</th><th>Payment</th><th>Balance left</th><th>Expected</th><th>Expiry and balance status</th></tr></thead>
          <tbody>{result.funding.map(row => <tr key={row.id}><th scope="row">{row.name}</th><td>{labels[row.kind]}</td>
            <td>{money(row.remaining_cents)}</td><td>{money(row.unreceived_cents)}</td>
            <td>{row.expiry ? <time dateTime={row.expiry}>{row.expiry}</time> : 'No expiry recorded'}
              {row.days_to_expiry !== null && row.days_to_expiry < 0 && <small>Expired</small>}
              {row.days_to_expiry !== null && row.days_to_expiry >= 0 && row.days_to_expiry <= 30 && <small>Expires within 30 days</small>}
              {row.low_balance && <small>15% or less remains</small>}
            </td>
          </tr>)}</tbody>
        </table></div> : <p>No funding sources in this year.</p>}
      </section>}
      <section className="panel">
        <h2>Spending estimate</h2>
        <p>{result.forecast.status}</p>
        {result.forecast.estimate && <p>{result.forecast.estimate.label} · {money(result.forecast.estimate.cash_cents)} cash
          {' · '}{money(result.forecast.estimate.credit_cents)} in purchasing credits. History covers {result.forecast.months.join(', ')}.</p>}
      </section>
    </>}
  </>;
}

function MonthlySpending({months}: {months: Spend[]}) {
  if (!months.length) return <p>No confirmed spending in this selection.</p>;
  const highest = Math.max(1, ...months.flatMap(row => kinds.map(kind => amount(row, kind))));
  return <div className="tablewrap"><table className="spending-trends">
    <thead><tr><th>Month</th>{kinds.map(kind => <th key={kind}>{labels[kind]}</th>)}</tr></thead>
    <tbody>{months.map(row => <tr key={row.label}><th scope="row">{row.label}</th>
      {kinds.map(kind => <td key={kind}>{money(amount(row, kind))}
        <meter className={kind} min={0} max={highest} value={amount(row, kind)} aria-hidden="true"/>
      </td>)}
    </tr>)}</tbody>
  </table></div>;
}
