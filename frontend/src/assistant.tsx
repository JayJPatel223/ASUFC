import {FormEvent, useState} from 'react';
import {Api, Program} from './api';

const topics = {
  overview: 'Summarize the ledger',
  cash_balance: 'Remaining cash',
  credit_balance: 'Remaining purchasing credits',
  budget_balance: 'Remaining program budgets',
  year_spending: 'Spending this academic year',
  last_month: 'Spending last month',
  expiring: 'Funding expiring soon',
  unused: 'Funding with an unused balance',
  expected: 'Funding we are waiting to receive',
  program_comparison: 'Compare program spending',
  allocation: 'Find eligible funding for a purchase',
  estimate: 'Spending estimate',
};

type Source = 'Reports' | 'Financial insights' | 'Funding & grants' | 'Transactions';
type Answer = {status: 'clarify'; message: string} | {
  status: 'answered';
  title: string;
  facts: string[];
  source: Source;
  year: string;
  program: string | null;
  pending_purchases: number;
};

export function FinanceAssistant({api, year, programs, openPage}: {
  api: Api; year: string; programs: Program[]; openPage: (page: Source) => void;
}) {
  const [question, setQuestion] = useState('');
  const [program, setProgram] = useState('');
  const [topic, setTopic] = useState('');
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function ask(selection: {question: string} | {topic: string}) {
    setAnswer(null);
    setError('');
    setBusy(true);
    try {
      setAnswer(await api<Answer>('/assistant/ask', 'POST', {year, program: program || null, ...selection}));
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (text) void ask({question: text});
  }

  return <>
    <section className="panel">
      <h2>Ask about the ledger</h2>
      <p>The offline assistant recognizes common finance questions and answers from the staff ledger.</p>
      <label>Program for assistant<select value={program} disabled={busy} onChange={event => {
        setProgram(event.target.value);
        setAnswer(null);
        setError('');
      }}>
        <option value="">All programs</option>
        {programs.map(row => <option key={row.code} value={row.code}>{row.name}</option>)}
      </select></label>
      <form onSubmit={submitQuestion}>
        <label>Question for the assistant
          <input value={question} onChange={event => setQuestion(event.target.value)}
            placeholder="How much cash funding remains?" maxLength={300} required disabled={busy}/>
        </label>
        <button disabled={busy || !question.trim()}>Ask assistant</button>
      </form>
      <form onSubmit={event => { event.preventDefault(); if (topic) void ask({topic}); }}>
        <label>Or choose a topic<select value={topic} onChange={event => setTopic(event.target.value)} disabled={busy}>
          <option value="">Choose a topic</option>
          {Object.entries(topics).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
        <button className="secondary" disabled={busy || !topic}>Show answer</button>
      </form>
      {busy && <p role="status">Reading the ledger…</p>}
      {error && <p role="alert" className="error">{error}</p>}
      {answer?.status === 'clarify' && <p role="status">{answer.message}</p>}
    </section>
    {answer?.status === 'answered' && <section className="panel" aria-live="polite">
      <h2>{answer.title}</h2>
      <p>{answer.year} · {answer.program || 'All programs'}</p>
      <ul>{answer.facts.map((fact, index) => <li key={index}>{fact}</li>)}</ul>
      {answer.pending_purchases > 0 && <p>
        {answer.pending_purchases} {answer.pending_purchases === 1 ? 'purchase is' : 'purchases are'} awaiting review in this scope.
        Confirmed spending and balances reflect posted allocations.
      </p>}
      <button className="secondary" onClick={() => openPage(answer.source)}>Open {answer.source}</button>
    </section>}
  </>;
}
