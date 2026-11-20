import React,{useState,useEffect,useMemo,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {makeApi,cents,money,Program,Funding,FundingEligibility,Budget,Transaction,Dashboard,Api,AuditEvent,downloadReport,FundingReceipt,AcademicPeriod,FundingTransfer} from './api';
import './style.css';
import {makeDemoApi} from './demo';
import {desktop, DesktopBackup} from './desktop-backup';
import {ReceiptFiles} from './receipt-files';
const DEMO=import.meta.env.MODE==='pages';
type Data={programs:Program[];funding:Funding[];budgets:Budget[];transactions:Transaction[];dashboard:Dashboard;audit:AuditEvent[];periods:AcademicPeriod[];transfers:FundingTransfer[]};
type Save=(path:string,body:unknown,method?:string)=>Promise<void>;
const pages=['Overview','Funding & grants','Programs & budgets','Transactions','History','Audit log','Reports','Academic years','Reconciliation','Excel import','Account'] as const;
type Page=typeof pages[number];
const field=(f:FormData,k:string)=>String(f.get(k)||'');
function Input({name,label,type='text',required=true,defaultValue}:{name:string;label:string;type?:string;required?:boolean;defaultValue?:string}){return <label>{label}<input name={name} type={type} required={required} defaultValue={defaultValue} step={type==='number'?'0.01':undefined} min={type==='number'?'0':undefined}/></label>}
function ProgramSelect({programs,name='program',optional=false}:{programs:Program[];name?:string;optional?:boolean}){return <select aria-label={name==="suggestProgram"?"Program for suggestion":optional?"Program restriction":"Program"} name={name} required={!optional}>{optional&&<option value="">All programs</option>}{programs.map(p=><option key={p.code} value={p.code}>{p.name} · {p.code}</option>)}</select>}
function Panel({title,children}:{title:string;children:React.ReactNode}){return <section className="panel"><h2>{title}</h2>{children}</section>}
function Form({children,onSubmit,button,busy}:{children:React.ReactNode;onSubmit:(data:FormData)=>Promise<void>;button:string;busy:boolean}){const [error,setError]=useState('');return <form onSubmit={async e=>{e.preventDefault();setError('');const el=e.currentTarget;try{await onSubmit(new FormData(el));el.reset()}catch(e){setError(String((e as Error).message))}}}>{children}{error&&<p role="alert" className="error">{error}</p>}<button disabled={busy} type="submit">{button}</button></form>}
function BalanceMetrics({values}: {values: [string, number][]}) {
  return <div className="balance-metrics">{values.map(([label, amount]) =>
    <div className="metric" key={label}><span>{label}</span><strong>{money(amount)}</strong></div>
  )}</div>;
}

function Overview({data, year, openPage}: {data: Data; year: string; openPage: (page: Page) => void}) {
  const cash = data.dashboard.funding.find(source => source.kind === 'cash');
  const credit = data.dashboard.funding.find(source => source.kind === 'credit');
  const funding = data.funding.filter(source => source.academic_year === year);
  const unallocated = (kind: Funding['kind']) => funding
    .filter(source => source.kind === kind)
    .reduce((total, source) => total + Number(source.unallocated_cents), 0);
  const today = new Date();
  const cutoff = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 30);
  const dateKey = (date: Date) => [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
  const todayKey = dateKey(today);
  const cutoffKey = dateKey(cutoff);
  const alerts = funding.flatMap(source => {
    const details = [];
    if (source.expiry && source.expiry <= cutoffKey && source.remaining_cents > 0) {
      details.push((source.expiry < todayKey ? 'Expired ' : 'Expires ') + source.expiry);
    }
    if (source.capacity_cents > 0 && source.remaining_cents <= source.capacity_cents * 0.15) {
      details.push('Low balance (' + money(source.remaining_cents) + ')');
    }
    return details.length ? [{source, details}] : [];
  });
  const recent = data.transactions
    .filter(purchase => purchase.status === 'confirmed' && purchase.allocations.some(row => row.academic_year === year))
    .sort((a, b) => b.purchase_date.localeCompare(a.purchase_date) || b.id - a.id)
    .slice(0, 5);

  return <>
    <div className="overview-actions">
      <button onClick={() => openPage('Transactions')}>Record a purchase</button>
      <button className="secondary" onClick={() => openPage('Reports')}>Open spending reports</button>
    </div>
    <div className="overview-columns">
      <section className="panel balance-panel" aria-labelledby="cash-overview">
        <h2 id="cash-overview">Cash</h2>
        <BalanceMetrics values={[
          ['Cash remaining', (cash?.capacity ?? 0) - (cash?.spent ?? 0)],
          ['Cash received', cash?.received ?? 0],
          ['Cash spent', cash?.spent ?? 0],
        ]}/>
      </section>
      <section className="panel balance-panel" aria-labelledby="credit-overview">
        <h2 id="credit-overview">Purchasing credits</h2>
        <BalanceMetrics values={[
          ['Credit remaining', (credit?.capacity ?? 0) - (credit?.spent ?? 0)],
          ['Credit received', credit?.received ?? 0],
          ['Credit used', credit?.spent ?? 0],
        ]}/>
      </section>
    </div>
    <div className="overview-columns">
      <section className="panel" aria-labelledby="funding-overview">
        <h2 id="funding-overview">Expected and unallocated funding</h2>
        <BalanceMetrics values={[
          ['Expected cash', cash?.expected ?? 0],
          ['Expected credit', credit?.expected ?? 0],
          ['Unallocated cash', unallocated('cash')],
          ['Unallocated credit', unallocated('credit')],
        ]}/>
        <p className="muted">Expected funds become available after receipt is confirmed. Check restrictions and expiry before allocating a balance.</p>
        <details>
          <summary>Carry-forward totals</summary>
          <dl className="carry-totals">
            <dt>Cash carried in</dt><dd>{money(cash?.carried_in ?? 0)}</dd>
            <dt>Cash carried out</dt><dd>{money(cash?.carried_out ?? 0)}</dd>
            <dt>Credit carried in</dt><dd>{money(credit?.carried_in ?? 0)}</dd>
            <dt>Credit carried out</dt><dd>{money(credit?.carried_out ?? 0)}</dd>
          </dl>
        </details>
      </section>
      <Panel title="Funding alerts">
        {alerts.length ? <ul className="funding-alerts">{alerts.map(({source, details}) =>
          <li className="warning" key={source.id}><strong>{source.name}</strong><span>{details.join(' · ')}</span></li>
        )}</ul> : <p>No low balances, upcoming expiry dates or expired balances in this year.</p>}
      </Panel>
    </div>
    <Panel title="Program utilization">
      {data.dashboard.programs.length ? data.dashboard.programs.map(program => {
        const name = data.programs.find(row => row.code === program.program_code)?.name ?? program.program_code;
        return <div className="barrow" key={program.program_code}>
          <div><b>{name}</b><span>{money(program.spent)} / {money(program.allocated)}</span></div>
          <progress aria-label={name + ' budget used'} max={program.allocated || 1} value={program.spent}/>
          <small>{money(program.allocated - program.spent)} remaining</small>
        </div>;
      }) : <p>No budgets for this year.</p>}
    </Panel>
    <Panel title="Recent confirmed purchases">
      {recent.length ? <div className="tablewrap"><table>
        <thead><tr><th scope="col">Date</th><th scope="col">Supplier</th><th scope="col">Total</th></tr></thead>
        <tbody>{recent.map(purchase => <tr key={purchase.id}>
          <td>{purchase.purchase_date}</td><td>{purchase.supplier}</td><td>{money(purchase.cents)}</td>
        </tr>)}</tbody>
      </table></div> : <p>No confirmed purchases for this year.</p>}
      <button className="secondary overview-link" onClick={() => openPage('History')}>View transaction history</button>
    </Panel>
    <Panel title="Funding balances"><FundingTable rows={funding}/></Panel>
  </>;
}
function FundingTable({rows}:{rows:Funding[]}){return <div className="tablewrap"><table><thead><tr><th scope="col">Source</th><th scope="col">Type</th><th scope="col">Received</th><th scope="col">Carried in</th><th scope="col">Carried out</th><th scope="col">Expected outstanding</th><th scope="col">Remaining</th><th scope="col">Unallocated</th></tr></thead><tbody>{rows.map(f=><tr key={f.id}><td>{f.name}<small>{fundingRuleSummary(f)}</small>{f.expiry&&<small>Expires <time dateTime={f.expiry}>{f.expiry}</time></small>}{!DEMO&&f.notes&&<small>{f.notes}</small>}</td><td>{f.kind}</td><td>{money(f.received_cents)}</td><td>{money(f.carried_in_cents)}</td><td>{money(f.carried_out_cents)}</td><td>{money(f.expected_cents-f.received_cents)}</td><td>{money(f.remaining_cents)}</td><td>{money(f.unallocated_cents)}</td></tr>)}</tbody></table>{!rows.length&&<p>No funding recorded.</p>}</div>}
function FundingPage({data,year,save,busy,api}:{data:Data;year:string;save:Save;busy:boolean;api:Api}){const rows=data.funding.filter(f=>f.academic_year===year);return <><div className="twocol"><Panel title="Add funding"><Form busy={busy} button="Save funding" onSubmit={async f=>save('/funding',{name:field(f,'name'),academic_year:year,kind:field(f,'kind'),expected_cents:cents(field(f,'award')),received_cents:cents(field(f,'received')),expiry:field(f,'expiry')||null,...(DEMO?{eligible_program:field(f,'program')||null,eligible_supplier:field(f,'supplier')||null}:readFundingRuleFields(f)),organization:field(f,'organization'),source_type:field(f,'source_type'),recurring:field(f,'recurring')==='yes',expected_date:field(f,'expected_date')||null,notes:field(f,'notes'),received_on:field(f,'received_on')||null})}><Input name="name" label="Funding source"/><Input name="organization" label="Funding organization" required={false}/><Input name="source_type" label="Funding classification" required={false}/><label>Recurring funding<select name="recurring"><option value="no">No / not confirmed</option><option value="yes">Yes</option></select></label><Input name="expected_date" label="Expected receipt date" type="date" required={false}/><Input name="received_on" label="Actual receipt date (if known)" type="date" required={false}/><Input name="notes" label="Grant notes" required={false}/><label>Funding type<select name="kind"><option value="cash">Cash</option><option value="credit">Purchasing credit</option></select></label><Input name="award" label="Total award (CAD)" type="number"/><Input name="received" label="Confirmed received (CAD)" type="number" defaultValue="0"/>{DEMO?<><label>Program restriction<ProgramSelect programs={data.programs} optional/></label><Input name="supplier" label="Supplier restriction" required={false}/></>:<FundingRuleFields programs={data.programs}/>}<Input name="expiry" label="Expiry date" type="date" required={false}/></Form></Panel><Panel title="Confirm funding received"><Form busy={busy} button="Update confirmed amount" onSubmit={async f=>save('/funding/'+field(f,'id')+'/received',{received_cents:cents(field(f,'total')),received_on:field(f,'received_on')||null},'PATCH')}><label>Funding source<select name="id" required><option value="">Select source</option>{rows.map(f=><option key={f.id} value={f.id}>{f.name} · received {money(f.received_cents)}</option>)}</select></label><Input name="total" label="New cumulative received amount (CAD)" type="number"/><Input name="received_on" label="Receipt date (if known)" type="date" required={false}/></Form></Panel></div><Panel title="Funding records"><FundingTable rows={rows}/></Panel>{!DEMO&&<><FundingRulesForm programs={data.programs} rows={rows} save={save} busy={busy}/><FundingExpiryForm rows={rows} save={save} busy={busy}/></>}<ReceiptHistory api={api} rows={rows}/><CarryForward data={data} year={year} save={save} busy={busy}/></>}
function fundingRules(funding?: Funding): FundingEligibility {
  return {
    eligible_programs: funding?.eligible_programs ?? (funding?.eligible_program ? [funding.eligible_program] : []),
    eligible_suppliers: funding?.eligible_suppliers ?? (funding?.eligible_supplier ? [funding.eligible_supplier] : []),
    eligible_purchase_types: funding?.eligible_purchase_types ?? (funding?.eligible_purchase_type ? [funding.eligible_purchase_type] : []),
  };
}
function fundingRuleSummary(funding: Funding) {
  const rules = fundingRules(funding);
  return [
    rules.eligible_programs.join(', ') || 'All programs',
    rules.eligible_suppliers.join(', '),
    rules.eligible_purchase_types.join(', '),
  ].filter(Boolean).join(' · ');
}
function readFundingRuleFields(form: FormData): FundingEligibility {
  return {
    eligible_programs: form.getAll('eligible_programs').map(String),
    eligible_suppliers: field(form, 'eligible_suppliers').split('\n').map(label => label.trim()).filter(Boolean),
    eligible_purchase_types: field(form, 'eligible_purchase_types').split('\n').map(label => label.trim()).filter(Boolean),
  };
}
function FundingRuleFields({programs, initial = fundingRules()}: {programs: Program[]; initial?: FundingEligibility}) {
  return <>
    <fieldset className="funding-programs">
      <legend>Eligible programs</legend>
      <p className="muted">Leave all unchecked to allow any program.</p>
      {programs.map(program => <label key={program.code}>
        <input type="checkbox" name="eligible_programs" value={program.code}
          defaultChecked={initial.eligible_programs.includes(program.code)}/>
        {program.name}
      </label>)}
    </fieldset>
    <label>Eligible suppliers (one per line)
      <textarea name="eligible_suppliers" rows={3} defaultValue={initial.eligible_suppliers.join('\n')}/>
    </label>
    <label>Eligible purchase types (one per line)
      <textarea name="eligible_purchase_types" rows={3} defaultValue={initial.eligible_purchase_types.join('\n')}/>
    </label>
    <p className="muted">Leave a list blank to allow any value. Use the supplier and purchase type names staff enter on purchases.</p>
  </>;
}
function FundingRulesForm({programs, rows, save, busy}: {programs: Program[]; rows: Funding[]; save: Save; busy: boolean}) {
  const [sourceId, setSourceId] = useState('');
  const source = rows.find(row => String(row.id) === sourceId);
  const initial = fundingRules(source);
  return <Panel title="Edit spending rules">
    <label>Funding source
      <select value={source ? sourceId : ''} onChange={event => setSourceId(event.target.value)}>
        <option value="">Choose source</option>
        {rows.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select>
    </label>
    {source && <Form key={source.id} busy={busy} button="Save spending rules" onSubmit={async form => save(
      '/funding/' + source.id + '/eligibility',
      {...readFundingRuleFields(form), expected: initial, reason: field(form, 'reason')},
      'PATCH',
    )}>
      <FundingRuleFields programs={programs} initial={initial}/>
      <Input name="reason" label="Reason"/>
    </Form>}
  </Panel>;
}
function FundingExpiryForm({rows, save, busy}: {rows: Funding[]; save: Save; busy: boolean}) {
  return <Panel title="Update funding expiry">
    <Form busy={busy} button="Save expiry" onSubmit={async form => save(
      '/funding/' + field(form, 'id') + '/expiry',
      {expiry: field(form, 'expiry') || null, reason: field(form, 'reason')},
      'PATCH',
    )}>
      <label>Funding source<select name="id" required>
        <option value="">Choose source</option>
        {rows.map(source => <option key={source.id} value={source.id}>
          {source.name} · {source.expiry ? 'Expires ' + source.expiry : 'No expiry recorded'}
        </option>)}
      </select></label>
      <Input name="expiry" label="New expiry date (leave blank to clear)" type="date" required={false}/>
      <Input name="reason" label="Reason"/>
    </Form>
  </Panel>;
}
function CarryForward({data,year,save,busy}:{data:Data;year:string;save:Save;busy:boolean}){const rows=data.funding.filter(f=>f.academic_year===year);const next=String(Number(year.slice(0,4))+1)+'-'+String(Number(year.slice(5))+1);return <><Panel title="Grant carry-forward permission"><Form busy={busy} button="Record permission" onSubmit={async f=>save('/funding/'+field(f,'id')+'/carry-permission',{eligible:field(f,'eligible')==='yes',reason:field(f,'reason')},'PATCH')}><label>Funding source<select name="id" required><option value="">Choose source</option>{rows.map(r=><option value={r.id} key={r.id}>{r.name} · {r.carry_eligible?'Eligible':'Not confirmed'}</option>)}</select></label><label>Grant permits carry-forward<select name="eligible"><option value="no">No / not confirmed</option><option value="yes">Yes — documented permission</option></select></label><Input name="reason" label="Evidence or reason"/></Form></Panel><Panel title="Transfer unused funding"><p className="muted">Release unused budget allocations first. Transfers preserve grant restrictions and do not create a new receipt. Both years must be configured.</p><Form busy={busy} button="Confirm transfer" onSubmit={async f=>{if(!window.confirm('Transfer this balance to the next academic year?'))throw new Error('No changes made.');await save('/funding/'+field(f,'id')+'/carry-forward',{destination_year:next,cents:cents(field(f,'amount')),reason:field(f,'reason')})}}><label>Eligible funding<select name="id" required><option value="">Choose source</option>{rows.filter(r=>r.carry_eligible).map(r=><option value={r.id} key={r.id}>{r.name} · {money(r.unallocated_cents)} unallocated</option>)}</select></label><p>Destination: {next} {data.periods.some(p=>p.academic_year===next)?'':'(not configured)'}</p><Input name="amount" label="Transfer amount (CAD)" type="number"/><Input name="reason" label="Transfer reason"/></Form></Panel><Panel title="Transfer history"><div className="tablewrap"><table><thead><tr><th>Source</th><th>From</th><th>To</th><th>Amount</th><th>Reason</th><th>Status</th></tr></thead><tbody>{data.transfers.filter(t=>t.source_year===year||t.destination_year===year).map(t=><tr key={t.id}><td>{t.funding_name} ({t.kind})</td><td>{t.source_year}</td><td>{t.destination_year}</td><td>{money(t.cents)}</td><td>{t.reason}</td><td>{t.reversed?"Reversed: "+t.reversal_reason:"Active"}</td></tr>)}</tbody></table></div><Form busy={busy} button="Reverse transfer" onSubmit={async f=>{if(!window.confirm("Reverse this transfer?"))throw new Error("No changes made.");await save("/funding-transfers/"+field(f,"transfer")+"/reverse",{reason:field(f,"reason")})}}><label>Transfer<select name="transfer" required><option value="">Choose active transfer</option>{data.transfers.filter(t=>!t.reversed&&(t.source_year===year||t.destination_year===year)).map(t=><option key={t.id} value={t.id}>{t.funding_name} · {money(t.cents)}</option>)}</select></label><Input name="reason" label="Reversal reason"/></Form></Panel></>}
function ReceiptHistory({api,rows}:{api:Api;rows:Funding[]}){const [id,setId]=useState('');const [receipts,setReceipts]=useState<FundingReceipt[]|null>(null);const [error,setError]=useState('');useEffect(()=>{let active=true;setReceipts(null);setError('');if(id)api<FundingReceipt[]>('/funding/'+id+'/receipts').then(r=>{if(active)setReceipts(r)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[api,id,rows]);return <Panel title="Funding receipt history"><label>Funding source<select value={id} onChange={e=>setId(e.target.value)}><option value="">Select funding source</option>{rows.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>{error&&<p role="alert">{error}</p>}{receipts&&<table><thead><tr><th>Received date</th><th>Amount</th><th>Recorded by</th></tr></thead><tbody>{receipts.map(r=><tr key={r.id}><td>{r.received_on||'Unknown'}</td><td>{money(r.cents)}</td><td>{r.actor}</td></tr>)}</tbody></table>}</Panel>}
function BudgetsPage({data,year,save,busy}:{data:Data;year:string;save:Save;busy:boolean}){return <><Panel title="Create custom program"><Form busy={busy} button="Add program" onSubmit={async f=>save('/programs',{code:field(f,'code').toUpperCase(),name:field(f,'name')})}><Input name="code" label="Program code"/><Input name="name" label="Program name"/></Form></Panel><Panel title="Allocate funding to a program"><Form busy={busy} button="Create budget allocation" onSubmit={async f=>save('/budgets',{funding_id:Number(field(f,'funding')),program_code:field(f,'program'),cents:cents(field(f,'amount'))})}><label>Funding source<select name="funding" required><option value="">Select funding</option>{data.funding.filter(f=>f.academic_year===year).map(f=><option key={f.id} value={f.id}>{f.name} · {money(f.unallocated_cents)} unallocated</option>)}</select></label><label>Program<ProgramSelect programs={data.programs}/></label><Input name="amount" label="Budget amount (CAD)" type="number"/></Form></Panel><Panel title="Adjust an existing budget"><Form busy={busy} button="Save adjustment" onSubmit={async f=>save('/budgets/'+field(f,'budget'),{cents:cents(field(f,'amount')),reason:field(f,'reason')},'PATCH')}><label>Budget<select name="budget" required><option value="">Select budget</option>{data.budgets.filter(b=>b.academic_year===year).map(b=><option key={b.id} value={b.id}>{b.program_code} · {b.funding_name} · {money(b.cents)}</option>)}</select></label><Input name="amount" label="New total budget (CAD)" type="number"/><Input name="reason" label="Reason for adjustment"/></Form></Panel><Panel title="Budget allocations"><div className="tablewrap"><table><thead><tr><th>Program</th><th>Funding</th><th>Allocated</th><th>Spent</th><th>Remaining</th></tr></thead><tbody>{data.budgets.filter(b=>b.academic_year===year).map(b=><tr key={b.id}><td>{b.program_code}</td><td>{b.funding_name} ({b.kind})</td><td>{money(b.cents)}</td><td>{money(b.cents-b.remaining)}</td><td>{money(b.remaining)}</td></tr>)}</tbody></table></div></Panel></>}
function PurchasePage({data,year,save,busy,api,original}:{data:Data;year:string;save:Save;busy:boolean;api:Api;original?:Transaction}){const [total,setTotal]=useState(original?(original.cents/100).toFixed(2):'');const [splits,setSplits]=useState(original?original.allocations.map((a,i)=>({id:i+1,budget:String(a.budget_id),amount:(a.cents/100).toFixed(2)})):[{id:1,budget:'',amount:''}]);const [next,setNext]=useState((original?.allocations.length||1)+1);const [suggesting,setSuggesting]=useState(false);const [suggestionMessage,setSuggestionMessage]=useState('');const safe=(v:string)=>{try{return cents(v)}catch{return 0}};const assigned=splits.reduce((n,s)=>n+safe(s.amount),0);const update=(id:number,key:'budget'|'amount',value:string)=>setSplits(old=>old.map(s=>s.id===id?{...s,[key]:value}:s));return <Panel title={original?"Correct purchase #"+original.id:"Record a purchase"}><Form busy={busy||suggesting} button={original?"Confirm linked correction":"Confirm and save purchase"} onSubmit={async f=>{const amount=cents(total);if(assigned!==amount)throw new Error('Split allocations must match total.');const payload={duplicate_reason:field(f,'duplicate_reason'),purchase_date:field(f,'date'),supplier:field(f,'supplier'),purchase_type:field(f,'type'),description:field(f,'description'),cents:amount,allocations:splits.map(s=>({budget_id:Number(s.budget),cents:cents(s.amount)}))};if(original){if(!window.confirm('Replace the original purchase and preserve its history?'))throw new Error('No changes made.');await save('/transactions/'+original.id+'/correct',{reason:field(f,'reason'),replacement:payload});}else await save('/transactions',payload);setTotal('');setSplits([{id:next,budget:'',amount:''}]);setNext(next+1)}}><div className="twocol"><Input name="date" label="Purchase date" type="date" defaultValue={original?.purchase_date}/><Input name="supplier" label="Supplier" defaultValue={original?.supplier}/><Input name="type" label="Purchase type" defaultValue={original?.purchase_type}/><Input name="description" label="Description" required={false} defaultValue={original?.description}/></div><label>Purchase total (CAD)<input type="number" required min=".01" step=".01" value={total} onChange={e=>setTotal(e.target.value)}/></label>{original?<Input name="reason" label="Correction reason"/>:<div className="suggestion"><h3>Find eligible funding</h3><p className="muted">Optional: select one program and payment type. The selected preferred grant is tried first, followed by eligible grants with earlier expiry dates. Review the suggested split before saving.</p><div className="twocol"><label>Program for suggestion<ProgramSelect programs={data.programs} name="suggestProgram"/></label><label>Payment type<select name="suggestKind"><option value="cash">Cash</option><option value="credit">Purchasing credit</option></select></label></div><label>Preferred funding<select name="suggestPreferred"><option value="">No preference</option>{data.funding.filter(f=>f.academic_year===year).map(f=><option value={f.id} key={f.id}>{f.name} ({f.kind})</option>)}</select></label><button type="button" className="secondary" disabled={busy||suggesting} onClick={async e=>{const form=e.currentTarget.form;if(!form)return;const f=new FormData(form);setSuggestionMessage('');setSuggesting(true);try{const date=field(f,'date'),supplier=field(f,'supplier'),amount=cents(total);if(!date||!supplier.trim()||amount<=0)throw new Error('Enter purchase date, supplier and positive total first.');const result=await api<{allocations:{budget_id:number;cents:number}[];unallocated_cents:number}>('/allocation-suggestions','POST',{program_code:field(f,'suggestProgram'),academic_year:year,kind:field(f,'suggestKind'),supplier,purchase_type:field(f,'type'),purchase_date:date,cents:amount,preferred_funding:Number(field(f,'suggestPreferred'))||null});if(result.allocations.length){setSplits(result.allocations.map((a,i)=>({id:next+i,budget:String(a.budget_id),amount:(a.cents/100).toFixed(2)})));setNext(next+result.allocations.length)}setSuggestionMessage(result.unallocated_cents>0?'Eligible allocated funding is short by '+money(result.unallocated_cents)+'. Review or adjust the allocations.':'Suggested allocations are ready for review. Nothing has been saved.')}catch(e){setSuggestionMessage((e as Error).message)}finally{setSuggesting(false)}}}>{suggesting?'Checking funding…':'Suggest allocations'}</button>{suggestionMessage&&<p role="status">{suggestionMessage}</p>}</div>}<Input name="duplicate_reason" label="Duplicate review reason (only if a matching purchase is legitimate)" required={false}/><h3>Program and funding allocations</h3>{splits.map(s=><div className="split" key={s.id}><label>Program / funding<select required value={s.budget} onChange={e=>update(s.id,'budget',e.target.value)}><option value="">Select budget</option>{data.budgets.filter(b=>b.academic_year===year).map(b=><option key={b.id} value={b.id}>{b.program_code} · {b.funding_name} · {money(b.remaining)} left</option>)}</select></label><label>Amount (CAD)<input required min=".01" step=".01" type="number" value={s.amount} onChange={e=>update(s.id,'amount',e.target.value)}/></label><button type="button" className="secondary" disabled={splits.length===1} onClick={()=>setSplits(splits.filter(x=>x.id!==s.id))}>Remove</button></div>)}<button className="secondary" type="button" onClick={()=>{setSplits([...splits,{id:next,budget:'',amount:''}]);setNext(next+1)}}>+ Add allocation</button><p>Allocated: <b>{money(assigned)}</b> · Unassigned: <b>{money(safe(total)-assigned)}</b></p></Form></Panel>}
function History({data,year,save,busy,api}:{data:Data;year:string;save:Save;busy:boolean;api:Api}){const [query,setQuery]=useState('');const [month,setMonth]=useState('');const [program,setProgram]=useState('');const [selected,setSelected]=useState('');const [correction,setCorrection]=useState('');const rows=data.transactions.filter(t=>t.allocations.some(a=>a.academic_year===year)&&(!month||t.purchase_date.startsWith(month))&&(!program||t.allocations.some(a=>a.program===program))&&JSON.stringify(t).toLowerCase().includes(query.toLowerCase()));return <><Panel title="Correct a transaction"><label>Confirmed purchase<select value={correction} onChange={e=>setCorrection(e.target.value)}><option value="">Select a purchase</option>{data.transactions.filter(t=>t.status==='confirmed'&&t.allocations.some(a=>a.academic_year===year)).map(t=><option key={t.id} value={t.id}>#{t.id} · {t.supplier} · {money(t.cents)}</option>)}</select></label></Panel>{correction&&<PurchasePage key={correction} original={data.transactions.find(t=>String(t.id)===correction&&t.status==='confirmed')} data={data} year={year} save={async(path,body,method)=>{await save(path,body,method);setCorrection('')}} busy={busy} api={api}/>}{!DEMO&&<ReceiptFiles api={api} transactions={data.transactions.filter(t=>t.allocations.some(a=>a.academic_year===year))}/>}<Panel title="Transaction history"><Form busy={busy} button="Confirm void" onSubmit={async f=>{if(!window.confirm('Void this purchase and restore its balances? The original record will remain in history.'))throw new Error('No changes made.');await save('/transactions/'+selected+'/void',{reason:field(f,'reason')});setSelected('')}}><label>Purchase to void<select required value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Select confirmed purchase</option>{data.transactions.filter(t=>t.status==='confirmed'&&t.allocations.some(a=>a.academic_year===year)).map(t=><option key={t.id} value={t.id}>#{t.id} · {t.supplier} · {money(t.cents)}</option>)}</select></label><Input name="reason" label="Reason for voiding"/></Form><p className="muted">Voiding restores balances without deleting history. Use the linked correction form above to replace a purchase atomically.</p><div className="filters"><label>Search<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Supplier, description, funding…"/></label><label>Month<input type="month" value={month} onChange={e=>setMonth(e.target.value)}/></label><label>Program<select value={program} onChange={e=>setProgram(e.target.value)}><option value="">All</option>{data.programs.map(p=><option key={p.code} value={p.code}>{p.name}</option>)}</select></label></div><div className="tablewrap"><table><thead><tr><th>Date / ID</th><th>Supplier</th><th>Description</th><th>Total</th><th>Status</th><th>Allocations</th></tr></thead><tbody>{rows.map(t=><tr key={t.id}><td>{t.purchase_date}<small>#{t.id}</small></td><td>{t.supplier}<small>{t.purchase_type}</small></td><td>{t.description}</td><td>{money(t.cents)}</td><td>{t.status}<small>{t.void_reason}</small>{t.original_id&&<small>Corrects #{t.original_id}</small>}{t.replacement_id&&<small>Replaced by #{t.replacement_id}</small>}</td><td>{t.allocations.map(a=><small key={a.budget_id}>{a.program} · {a.funding} ({a.kind}) · {money(a.cents)}</small>)}</td></tr>)}</tbody></table>{!rows.length&&<p>No matching transactions.</p>}</div></Panel></>}
function AuditLog({events}:{events:AuditEvent[]}){return <Panel title="Financial audit log"><p className="muted">Latest 500 events across all academic years. Existing records made before audit tracking began may not have an event.</p><div className="tablewrap"><table><thead><tr><th>Recorded</th><th>Actor</th><th>Action</th><th>Record</th><th>Details</th></tr></thead><tbody>{events.map(e=><tr key={e.id}><td>{new Date(e.created_at).toLocaleString()}</td><td>{e.actor}</td><td>{e.action}</td><td>{e.entity} #{e.entity_id}</td><td><details><summary>View details</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(e.details,null,2)}</pre></details></td></tr>)}</tbody></table>{!events.length&&<p>No audit events yet.</p>}</div></Panel>}
type ReportRow={label:string;cash_cents:number;credit_cents:number};
type SpendingReport={totals:{cash_cents:number;credit_cents:number};purchase_count:number;month:ReportRow[];program:ReportRow[];supplier:ReportRow[];funding:ReportRow[]};
function Reports({api,year,data}:{api:Api;year:string;data:Data}) {
 const [start,setStart]=useState(''),[end,setEnd]=useState(''),[program,setProgram]=useState(''),[supplier,setSupplier]=useState(''),[funding,setFunding]=useState(''),[purchaseType,setPurchaseType]=useState('');
 const [exporting,setExporting]=useState(false),[exportError,setExportError]=useState('');
 const semesters = data.periods.find(period => period.academic_year === year)?.semesters ?? [];
 const selectedSemester = semesters.find(semester => semester.starts_on === start && semester.ends_on === end);
 const params=new URLSearchParams({year});for(const [k,v] of Object.entries({start,end,program,supplier,funding_id:funding,purchase_type:purchaseType}))if(v)params.set(k,v);const query=params.toString();
 const [report,setReport]=useState<SpendingReport|null>(null),[error,setError]=useState('');
 useEffect(()=>{let active=true;setReport(null);setError('');api<SpendingReport>('/reports/spending?'+query).then(r=>{if(active)setReport(r)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[api,query]);
 const table=(title:string,rows:ReportRow[])=><Panel title={title}><div className="tablewrap"><table><thead><tr><th>Group</th><th>Cash spent</th><th>Credit used</th></tr></thead><tbody>{rows.map(r=><tr key={r.label}><td>{r.label}</td><td>{money(r.cash_cents)}</td><td>{money(r.credit_cents)}</td></tr>)}</tbody></table>{!rows.length&&<p>No matching spending.</p>}</div></Panel>;
 return <><Panel title="Spending report filters"><label>Configured semester<select value={selectedSemester?.id ?? ''} onChange={e => {
   const semester = semesters.find(term => String(term.id) === e.target.value);
   setStart(semester?.starts_on ?? '');
   setEnd(semester?.ends_on ?? '');
 }}><option value="">Custom dates / entire year</option>{semesters.map(term => <option key={term.id} value={term.id}>{term.name}</option>)}</select></label>
 <p className="muted">Set From and To to include summer and between-term purchases within the selected academic year.</p>
 {(start || end) && <button type="button" onClick={() => {setStart('');setEnd('');}}>Clear report dates</button>}
 <div className="filters"><label>From<input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label>To<input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label><label>Program<select value={program} onChange={e=>setProgram(e.target.value)}><option value="">All programs</option>{data.programs.map(p=><option key={p.code} value={p.code}>{p.name}</option>)}</select></label><label>Supplier (exact name)<input value={supplier} onChange={e=>setSupplier(e.target.value)}/></label><label>Funding source<select value={funding} onChange={e=>setFunding(e.target.value)}><option value="">All sources</option>{data.funding.filter(f=>f.academic_year===year).map(f=><option key={f.id} value={f.id}>{f.name}</option>)}</select></label></div><label>Purchase type (exact name)<input value={purchaseType} onChange={e=>setPurchaseType(e.target.value)}/></label><button disabled={!report||exporting} onClick={async()=>{setExporting(true);setExportError('');try{await downloadReport(api,'/reports/spending.xlsx?'+query)}catch(e){setExportError((e as Error).message)}finally{setExporting(false)}}}>{exporting?'Exporting…':'Download Excel report'}</button>{exportError&&<p role="alert" className="error">{exportError}</p>}<p className="muted">Reports exclude voided purchases. Filtered totals reflect only matching allocations, not the entire purchase.</p></Panel>{error?<p role="alert" className="error">{error}</p>:!report?<p>Loading report…</p>:<><div className="metrics">{[['Cash spent',money(report.totals.cash_cents)],['Credit used',money(report.totals.credit_cents)],['Matching purchases',report.purchase_count]].map(([k,v])=><article className="metric" key={k}><span>{k}</span><strong>{v}</strong></article>)}</div><Panel title="Monthly spending trend">{report.month.length?report.month.map(r=><div className="barrow" key={r.label}><div><b>{r.label}</b><span>{money(r.cash_cents)} cash · {money(r.credit_cents)} credit</span></div><div style={{display:'flex',height:12,background:'#eee',borderRadius:6,overflow:'hidden',gap:0}}><span style={{background:'#702d42',width:(100*r.cash_cents/Math.max(1,...report.month.map(x=>x.cash_cents+x.credit_cents)))+'%'}}/><span style={{background:'#487d70',width:(100*r.credit_cents/Math.max(1,...report.month.map(x=>x.cash_cents+x.credit_cents)))+'%'}}/></div></div>):<p>No spending in selected period.</p>}</Panel>{table('Monthly spending',report.month)}{table('Program spending',report.program)}{table('Supplier spending',report.supplier)}{table('Funding source spending',report.funding)}</>}</>;
}
function AcademicYears({data,save,busy}:{data:Data;save:Save;busy:boolean}){return <><Panel title="Create academic year"><Form busy={busy} button="Create year" onSubmit={async f=>save('/academic-years',{academic_year:field(f,'year'),starts_on:field(f,'start'),ends_on:field(f,'end')})}><Input name="year" label="Academic year (YYYY-YYYY)"/><Input name="start" label="Start date" type="date"/><Input name="end" label="End date" type="date"/></Form></Panel><Panel title="Configure semester"><Form busy={busy} button="Add semester" onSubmit={async f=>save('/academic-years/'+encodeURIComponent(field(f,'year'))+'/semesters',{name:field(f,'name'),starts_on:field(f,'start'),ends_on:field(f,'end')})}><label>Academic year<select name="year" required><option value="">Select configured year</option>{data.periods.map(p=><option key={p.id} value={p.academic_year}>{p.academic_year}</option>)}</select></label><Input name="name" label="Semester name"/><Input name="start" label="Start date" type="date"/><Input name="end" label="End date" type="date"/></Form></Panel><Panel title="Adjust configured periods"><Form busy={busy} button="Save year dates" onSubmit={async f=>save("/academic-years/"+field(f,"year"),{starts_on:field(f,"start"),ends_on:field(f,"end"),reason:field(f,"reason")},"PATCH")}><label>Year<select name="year" required><option value="">Select year</option>{data.periods.map(p=><option key={p.id}>{p.academic_year}</option>)}</select></label><Input name="start" label="New start date" type="date"/><Input name="end" label="New end date" type="date"/><Input name="reason" label="Reason"/></Form><Form busy={busy} button="Save semester dates" onSubmit={async f=>{const [year,id]=field(f,"semester").split("/");await save("/academic-years/"+year+"/semesters/"+id,{name:field(f,"name"),starts_on:field(f,"start"),ends_on:field(f,"end"),reason:field(f,"reason")},"PATCH")}}><label>Semester<select name="semester" required><option value="">Select semester</option>{data.periods.flatMap(p=>p.semesters.map(t=><option key={t.id} value={p.academic_year+"/"+t.id}>{p.academic_year} · {t.name}</option>))}</select></label><Input name="name" label="Semester name"/><Input name="start" label="New start date" type="date"/><Input name="end" label="New end date" type="date"/><Input name="reason" label="Reason"/></Form></Panel>{data.periods.map(p=><Panel key={p.id} title={p.academic_year}><p>{p.starts_on} – {p.ends_on}</p><table><thead><tr><th>Semester</th><th>Start</th><th>End</th></tr></thead><tbody>{p.semesters.map(t=><tr key={t.id}><td>{t.name}</td><td>{t.starts_on}</td><td>{t.ends_on}</td></tr>)}</tbody></table></Panel>)}</>}
type ReconciliationResult={ok:boolean;issues:{code:string;record_id:number;expected:number|string;actual:number|string}[];funding:{id:number;name:string;kind:string;received_cents:number;carried_in_cents:number;carried_out_cents:number;allocated_cents:number;spent_cents:number;remaining_cents:number;unallocated_cents:number}[];budgets:{id:number;funding_id:number;program_code:string;allocated_cents:number;spent_cents:number;remaining_cents:number}[]};
function Reconciliation({api,year}:{api:Api;year:string}){
 const [r,setR]=useState<ReconciliationResult|null>(null),[error,setError]=useState(''),[version,setVersion]=useState(0),[exporting,setExporting]=useState(false);
 useEffect(()=>{let active=true;setR(null);setError('');api<ReconciliationResult>('/reports/reconciliation?year='+encodeURIComponent(year)).then(x=>{if(active)setR(x)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[api,year,version]);
 return <><Panel title="Internal ledger consistency"><p className="muted">Checks recorded receipts, transfers, budget limits and purchase allocations. Does not verify external bank statements.</p><button onClick={()=>setVersion(v=>v+1)}>Run checks</button> <button disabled={!r||exporting} onClick={async()=>{setExporting(true);try{await downloadReport(api,'/reports/reconciliation.xlsx?year='+encodeURIComponent(year),'asufc-balances.xlsx')}catch(e){setError((e as Error).message)}finally{setExporting(false)}}}>{exporting?'Exporting…':'Download balance workbook'}</button>{error&&<p role="alert">{error}</p>}{r?<p className={r.ok?'success':'error'}>{r.ok?(DEMO?'Demo balance summary — not server reconciliation':'No internal inconsistencies detected'):r.issues.length+' inconsistencies detected'}</p>:!error&&<p>Checking…</p>}{r?.issues.map((i,n)=><p key={n}>{i.code} · record #{i.record_id} · expected {i.expected}, actual {i.actual}</p>)}</Panel>{r&&<><Panel title="Funding balances"><div className="tablewrap"><table><thead><tr>{['Source','Received','Carry in','Carry out','Allocated','Spent','Remaining','Unallocated'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{r.funding.map(f=><tr key={f.id}><td>{f.name} ({f.kind})</td>{[f.received_cents,f.carried_in_cents,f.carried_out_cents,f.allocated_cents,f.spent_cents,f.remaining_cents,f.unallocated_cents].map((v,i)=><td key={i}>{money(v)}</td>)}</tr>)}</tbody></table></div></Panel><Panel title="Budget balances"><div className="tablewrap"><table><thead><tr><th>Program</th><th>Funding ID</th><th>Allocated</th><th>Spent</th><th>Remaining</th></tr></thead><tbody>{r.budgets.map(b=><tr key={b.id}><td>{b.program_code}</td><td>{b.funding_id}</td><td>{money(b.allocated_cents)}</td><td>{money(b.spent_cents)}</td><td>{money(b.remaining_cents)}</td></tr>)}</tbody></table></div></Panel></>}</>;
}
function ExcelImport({api,data,onImported}:{api:Api;data:Data;onImported:(count:number)=>void}){
 const keys=['external_id','purchase_date','supplier','purchase_type','description','amount','budget_id'];
 const [content,setContent]=useState(''),[sheet,setSheet]=useState('Sheet'),[mapping,setMapping]=useState<Record<string,string>>(Object.fromEntries(keys.map(k=>[k,k]))),[result,setResult]=useState<{valid:boolean;rows:{row:number;external_id:string;supplier:string;cents:number}[];errors:{row:number;error:string}[];validation_error?:string}|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const payload={content_base64:content,sheet,mapping};
 return <><Panel title="Import historical transactions"><p>Upload XLSX with one allocation per row. For split purchases, repeat the external ID and identical purchase details with a different budget ID and allocation amount. Map all seven fields.</p><input type="file" accept=".xlsx" onChange={async e=>{setResult(null);setContent('');setError('');const file=e.target.files?.[0];if(!file)return;if(file.size>5000000){setError('Maximum file size is 5 MB');return}try{const bytes=new Uint8Array(await file.arrayBuffer());let raw='';for(let i=0;i<bytes.length;i+=8192)raw+=String.fromCharCode(...bytes.subarray(i,i+8192));setContent(btoa(raw))}catch{setError('Unable to read workbook')}}}/><label>Worksheet name<input value={sheet} onChange={e=>{setSheet(e.target.value);setResult(null)}}/></label><div className="twocol">{keys.map(k=><label key={k}>{k}<input value={mapping[k]} onChange={e=>{setMapping({...mapping,[k]:e.target.value});setResult(null)}}/></label>)}</div><button disabled={!content||busy} onClick={async()=>{setBusy(true);setError('');setResult(null);try{setResult(await api('/imports/preview','POST',payload))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>Validate and preview</button>{error&&<p role="alert">{error}</p>}{result&&<><p>{result.valid?'Validation passed; nothing saved.':'Validation failed.'}</p>{result.validation_error&&<p>{result.validation_error}</p>}{result.errors.map(e=><p key={e.row}>Row {e.row}: {e.error}</p>)}<table><thead><tr><th>Row</th><th>External ID</th><th>Supplier</th><th>Amount</th></tr></thead><tbody>{result.rows.map(r=><tr key={r.row}><td>{r.row}</td><td>{r.external_id}</td><td>{r.supplier}</td><td>{money(r.cents)}</td></tr>)}</tbody></table><button disabled={!result.valid||busy} onClick={async()=>{if(!window.confirm('Import all validated purchases?'))return;setBusy(true);try{const r=await api<{imported:number}>('/imports/commit','POST',payload);setResult(null);setContent('');onImported(r.imported)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>Confirm import</button></>}</Panel><Panel title="Budget IDs for mapping"><table><thead><tr><th>ID</th><th>Year</th><th>Program</th><th>Funding</th></tr></thead><tbody>{data.budgets.map(b=><tr key={b.id}><td>{b.id}</td><td>{b.academic_year}</td><td>{b.program_code}</td><td>{b.funding_name}</td></tr>)}</tbody></table></Panel></>
}
function Account({api,onChanged}:{api:Api;onChanged:()=>void}){const [busy,setBusy]=useState(false);return <Panel title="Change staff password"><p>Changing your password signs out every active session.</p><Form busy={busy} button="Change password" onSubmit={async f=>{if(field(f,'new')!==field(f,'repeat'))throw new Error('Passwords differ');setBusy(true);try{await api('/auth/password','POST',{current_password:field(f,'current'),new_password:field(f,'new')});onChanged()}finally{setBusy(false)}}}><Input name="current" label="Current password" type="password"/><Input name="new" label="New password (minimum 16 characters)" type="password"/><Input name="repeat" label="Repeat new password" type="password"/></Form></Panel>}
function Workspace({api,logout}:{api:Api;logout:()=>void}){const [year,setYear]=useState('2026-2027');const [page,setPage]=useState<Page>('Overview');const [data,setData]=useState<Data|null>(null);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [message,setMessage]=useState('');const [version,setVersion]=useState(0);
const heading = useRef<HTMLHeadingElement>(null);
const openPage = (next: Page) => {
  setPage(next);
  setMessage('');
  requestAnimationFrame(() => heading.current?.focus());
};
useEffect(()=>{let active=true;setData(null);setError('');Promise.all([api<Program[]>('/programs'),api<Funding[]>('/funding'),api<Budget[]>('/budgets'),api<Transaction[]>('/transactions'),api<Dashboard>('/dashboard?year='+encodeURIComponent(year)),api<AuditEvent[]>('/audit'),api<AcademicPeriod[]>('/academic-years'),api<FundingTransfer[]>('/funding-transfers')]).then(([programs,funding,budgets,transactions,dashboard,audit,periods,transfers])=>{if(active)setData({programs,funding,budgets,transactions,dashboard,audit,periods,transfers})}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[api,year,version]);
const save:Save=async(path,body,method='POST')=>{setBusy(true);setMessage('');try{await api(path,method,body);setMessage('Record saved successfully.');setVersion(v=>v+1)}finally{setBusy(false)}};
return <div className="shell"><a className="skip-link" href="#workspace-main">Skip to content</a><aside><div className="brand">ASUFC<span>FINANCE WORKSPACE</span></div><nav aria-label="Finance workspace">{pages.map(p=><button className={page===p?'active':''} aria-current={page===p?'page':undefined} key={p} onClick={()=>openPage(p)}>{p}</button>)}</nav><button className="logout" onClick={logout}>Sign out</button></aside><main id="workspace-main" tabIndex={-1}>{DEMO&&<div className="demo-banner" role="note"><strong>Public demonstration — fictional data only.</strong> Changes stay in this tab and reset on reload. Server-only operations (Excel import/export, grant transfers, restriction edits, password changes and period edits) are unavailable. Never enter real records.</div>}<header><div><div className="eyebrow">{desktop?'STAFF DESKTOP LEDGER':'INTERNAL ADMINISTRATION · DEVELOPMENT'}</div><h1 ref={heading} tabIndex={-1}>{page}</h1></div><label>Academic year<select aria-label="Academic year" value={year} onChange={e=>setYear(e.target.value)}>{Array.from(new Set([year,"2026-2027",...(data?.periods||[]).map(p=>p.academic_year),...(data?.funding||[]).map(f=>f.academic_year)])).sort().map(y=><option key={y}>{y}</option>)}</select></label></header>{message&&<p role="status" className="success">{message}</p>}{error?<p role="alert" className="error">{error} <button onClick={()=>setVersion(v=>v+1)}>Retry</button></p>:!data?<p>Loading financial records…</p>:page==='Overview'?<Overview data={data} year={year} openPage={openPage}/>:page==='Funding & grants'?<FundingPage data={data} year={year} save={save} busy={busy} api={api}/>:page==='Programs & budgets'?<BudgetsPage data={data} year={year} save={save} busy={busy}/>:page==='Transactions'?<PurchasePage data={data} year={year} save={save} busy={busy} api={api}/>:page==='History'?<History key={year} data={data} year={year} save={save} busy={busy} api={api}/>:page==='Audit log'?<AuditLog events={data.audit}/>:page==='Reports'?<Reports key={year} data={data} year={year} api={api}/>:page==='Academic years'?<AcademicYears data={data} save={save} busy={busy}/>:page==='Reconciliation'?<Reconciliation api={api} year={year}/>:page==='Account'?<><Account api={api} onChanged={logout}/>{desktop&&<DesktopBackup api={api}/>}</>:<ExcelImport api={api} data={data} onImported={count=>{setMessage(count+' purchases imported.');setVersion(v=>v+1)}}/>}</main></div>}
function App(){const [authenticated,setAuthenticated]=useState(false),[checking,setChecking]=useState(true),[error,setError]=useState(''),[busy,setBusy]=useState(false);const api=useMemo(()=>DEMO?makeDemoApi():makeApi(),[]);useEffect(()=>{api('/auth/session').then(()=>setAuthenticated(true)).catch(()=>{}).finally(()=>setChecking(false))},[api]);if(checking)return <p>Checking staff session…</p>;if(authenticated)return <Workspace api={api} logout={()=>{api('/auth/logout','POST').then(()=>setAuthenticated(false)).catch(e=>{setError(e.message);setAuthenticated(false)})}}/>;return <div className="login"><Panel title="ASUFC Finance"><p>{DEMO?'Public demonstration. All records are fictional. No server or real authentication is connected.':desktop?'Offline staff ledger. Sign in with your local staff password.':'Staff-only development workspace. Use fictional records only.'}</p>{DEMO?<button onClick={async()=>{await api('/auth/login','POST',{username:'demo',password:'demo'});setAuthenticated(true)}}>Enter public demo</button>:<form onSubmit={async e=>{e.preventDefault();const el=e.currentTarget;const f=new FormData(el);setBusy(true);setError('');try{await api('/auth/login','POST',{username:field(f,'user'),password:field(f,'password')});el.reset();setAuthenticated(true)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}><Input name="user" label="Username" defaultValue={desktop?'staff':undefined}/><Input name="password" label="Password" type="password"/>{error&&<p role="alert" className="error">{error}</p>}<button disabled={busy}>Sign in</button></form>}</Panel></div>}
createRoot(document.getElementById('root')!).render(<App/>);
