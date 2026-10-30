import { useEffect, useState } from 'react'
import { api } from '../api'
import { Cite, Counts, fmtDate, fmtTime, Loading, Tip } from '../ui'

export default function Evaluation() {
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState('')
  useEffect(() => { api('/api/eval').then(setD).catch((e) => setErr(e.message)) }, [])
  if (err) return <div className="note bad">{err}</div>
  if (!d) return <Loading />
  const rp = d.replay, real = d.real, demo = d.demo || {}
  const [age, cd, early] = rp.methods
  const maxLead = 100
  return <div>
    <div className="titlebar"><div><h1>Test results</h1><div className="sub">scripts/evaluate.py · run {fmtTime(d.generated)}</div></div></div>
    <Counts items={[
      { k: 'r', v: `${d.routing.passed}/${d.routing.cases}`, l: 'Routing cases match APH Table 2.3', color: d.routing.passed === d.routing.cases ? 'green' : 'red' },
      { k: 'u', v: `${d.rules.passed}/${d.rules.cases}`, l: 'Rule calculations correct', color: d.rules.passed === d.rules.cases ? 'green' : 'red' },
      { k: 'c', v: `${100 - age.share_warned}%`, l: 'of late decisions had no overdue step at all (invisible to pendency alerts)', color: 'orange' },
      { k: 'p', v: `${early.precision}% vs ${age.precision}%`, l: 'warnings that were right: countdown vs per-step alerts', color: 'green' },
      { k: 'a', v: demo.chain_ok ? 'Intact' : '—', l: `Activity log, ${demo.audit_entries ?? '—'} entries`, color: demo.chain_ok ? 'green' : undefined }]} />

    <div className="box"><div className="bh"><h2>Alert timeliness <Tip>{rp.note}</Tip></h2><span className="small faint">{rp.applications} simulated applications over {rp.seasons} cycles; {rp.missed} ({rp.missed_share}%) decided after {fmtDate(rp.deadline)}</span></div>
      <div className="tablewrap"><table className="t small">
        <thead><tr><th>Method</th><th className="num">Late decisions warned</th><th className="num">Warned 3+ weeks ahead</th><th className="num">Warned while still saveable <Tip>On the day of its first warning, holding the remaining committees at minimum notice could still have made the date.</Tip></th><th className="num">Median days ahead</th><th className="num">Warnings that were right</th><th className="num">On-time applications wrongly flagged</th></tr></thead>
        <tbody>{rp.methods.map((m: any) => <tr key={m.name}><td><b>{m.name}</b><div className="faint">{m.how}</div></td>
          <td className="num">{m.share_warned}%</td><td className="num">{m.share_warned_21}%</td><td className="num">{m.share_saveable}%</td><td className="num">{m.median_lead ?? '—'}</td>
          <td className="num"><b>{m.precision}%</b></td><td className="num">{m.false_alarms}%</td></tr>)}</tbody></table></div>
      <div className="bb">
        <div className="small faint" style={{ marginBottom: 4 }}>Warnings that were right (the application really was going to be decided late)</div>
        {rp.methods.map((m: any, i: number) => <div key={m.name} className="hbar"><span className="k">{m.name}</span><span className="track"><i style={{ width: `${(m.precision / maxLead) * 100}%`, background: i ? 'var(--green)' : undefined }} /></span><span className="n">{m.precision}%</span></div>)}
        <p className="small muted"><b>{100 - age.share_warned}% of late decisions never had a single step past its time allowed</b>: every office was on time, and the application still missed the date. Per-step alerts cannot see these; the countdown flagged {cd.share_warned}% of all late decisions.
          Its early warning caught {early.share_saveable}% while fast-tracking could still save them (per-step alerts: {age.share_saveable}%), but {early.precision}% of its warnings were right against {age.precision}%,
          and it flagged {early.false_alarms}% of on-time applications against {age.false_alarms}%. Per-step alerts went off on {age.flagged} of {rp.applications} applications: officers cannot tell which overdue file matters.</p>
      </div></div>

    <div className="grid g2">
      <div className="box"><div className="bh"><h2>Real data</h2></div><div className="bb small">
        <p style={{ marginTop: 0 }}><b>{real.letters}</b> public AICTE approval letters of <b>{real.institutions}</b> institutions, each kept with its source URL and SHA-256.
          <b> {real.with_deficiencies}</b> of them ({real.share_with_deficiencies}%) granted approval with deficiencies to be complied with by a stated date. Each becomes a tracked undertaking.</p>
        <p>Where the next year's letter is also public ({real.pairs} cases), the same deficiency was noted again in <b>{real.noted_again}</b>:</p>
        <ul className="defs">{real.examples.map((x: string) => <li key={x}>{x}</li>)}</ul>
        <p>Time limits read from the letters: {Object.entries(real.windows).map(([k, v]) => `${k}: ${v}`).join(' · ')}.</p>
        <p>{real.aph_clauses} handbook clauses cited by the rules are located on their pages <Cite c={{ key: 'T2_3', ref: 'e.g. Table 2.3' }} /></p></div></div>
      <div className="box"><div className="bh"><h2>Follow-up and audit (demo cycle)</h2></div><div className="bb small">
        <p style={{ marginTop: 0 }}><b>{demo.messages}</b> reminders, notices and escalations went out by themselves for {demo.applications} applications ({demo.per_application} each), every one logged with date and channels:</p>
        <table className="t small"><tbody>{Object.entries(demo.by_kind || {}).sort((a: any, b: any) => b[1] - a[1]).map(([k, v]) => <tr key={k}><td>{k.replace('_', ' ')}</td><td className="num">{v as number}</td></tr>)}</tbody></table>
        <p>{demo.movements_logged} of {demo.movements} movements, decisions and submissions have their activity-log entry; the chain of fingerprints is {demo.chain_ok ? 'intact' : 'broken'}.</p></div></div>
    </div>

    <div className="box"><div className="bh"><h2>Routing against APH Table 2.3</h2><span className="small faint">{d.routing.natures} natures of application, each driven through the workflow engine in several outcome scenarios <Cite c={{ key: 'T2_3', ref: 'Table 2.3' }} /></span>
      <button className="btn sm" onClick={() => setOpen(open === 'r' ? '' : 'r')}>{open === 'r' ? 'Hide' : 'Show'} all {d.routing.cases}</button></div>
      {open === 'r' && <div className="tablewrap"><table className="t small"><thead><tr><th>Nature</th><th>Scenario</th><th>Path taken</th><th>Result</th></tr></thead>
        <tbody>{d.routing.rows.map((r: any, i: number) => <tr key={i}><td>{r.label}</td><td>{r.scenario.replace('_', ' ')}</td><td className="small">{r.path}</td>
          <td>{r.ok ? <span className="st green">matches</span> : <span className="st red">{r.problems.join('; ')}</span>}</td></tr>)}</tbody></table></div>}</div>

    <div className="box"><div className="bh"><h2>Rule calculations</h2></div>
      <div className="tablewrap"><table className="t small"><thead><tr><th>Rule</th><th>Case</th><th>Expected</th><th>Got</th><th /></tr></thead>
        <tbody>{d.rules.rows.map((r: any, i: number) => <tr key={i}><td>{r.rule} <Cite c={{ key: r.cite, ref: '' }} label="clause" /></td><td>{r.case}</td><td className="mono">{r.expected}</td><td className="mono">{r.got}</td>
          <td>{r.ok ? <span className="st green">ok</span> : <span className="st red">wrong</span>}</td></tr>)}</tbody></table></div></div>
  </div>
}
