import { useEffect, useState } from 'react'
import { api } from '../api'
import { useClock, useUser } from '../App'
import { Cite, fmtDate, fmtLong, Loading, Tip } from '../ui'

function SystemDate() {
  const { clock, move } = useClock()
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  if (!clock?.demo) return null
  const go = async (n: number) => { setBusy(true); try { await move(n) } finally { setBusy(false) } }
  const reload = async () => {
    if (!window.confirm('Reload the sample data? Everything recorded since will be replaced.')) return
    setBusy(true)
    try { await api('/api/admin/reset', { method: 'POST' }); window.location.reload() } catch (e: any) { setMsg(e.message); setBusy(false) }
  }
  return <div className="box"><div className="bh"><h2>System date</h2><span className="small faint">reminders and escalations are checked for every day the date moves</span></div>
    <div className="bb row"><b>{fmtLong(clock.today)}</b>
      <button className="btn sm" disabled={busy} onClick={() => go(1)}>Advance one day</button>
      <button className="btn sm" disabled={busy} onClick={() => go(7)}>Advance one week</button>
      <button className="btn sm" disabled={busy} onClick={reload}>Reload sample data</button>
      {busy && <span className="spinner" />}{msg && <span className="small" style={{ color: 'var(--red)' }}>{msg}</span>}</div></div>
}

const COL = (v: boolean | 'AA') => v === 'AA' ? <span className="pill orange" title="As applicable, depending on the outcome of the previous steps">AA</span> : v ? <span className="pill green">Yes</span> : <span className="faint">–</span>

export default function Rules() {
  const u = useUser()
  const admin = u.role === 'admin'
  const [d, setD] = useState<any>(null)
  const [msg, setMsg] = useState('')
  const load = () => api('/api/rules').then(setD)
  useEffect(() => { load() }, [])
  if (!d) return <Loading />
  const save = async (key: string, value: any) => {
    const reason = window.prompt(`Reason for changing ${key}?`)
    if (!reason || reason.length < 5) return
    try { await api('/api/settings', { method: 'PUT', json: { key, value, reason } }); setMsg(`Saved ${key}. The change is in the activity log.`); load() } catch (e: any) { setMsg(e.message) }
  }
  const Num = ({ k, v }: { k: string; v: number }) => admin ? <EditNum v={v} onSave={(x) => save(k, x)} /> : <span>{v}</span>
  const C = (k: string) => d.cites[k]
  return <div>
    <div className="titlebar"><div><h1>Rules <Tip>Everything the system does follows these settings. Routes are APH Table 2.3 as written; time limits the handbook leaves open are the administrator's. Click any clause to see it on the handbook page.</Tip></h1>
      <div className="sub">Approval Process Handbook 2024-27 · {admin ? 'you can change values; each change asks for a reason and is logged' : 'read only'}</div></div></div>
    {msg && <div className="note ok" style={{ marginBottom: 12 }}>{msg}</div>}
    {admin && <div style={{ marginBottom: 14 }}><SystemDate /></div>}

    <div className="box"><div className="bh"><h2>Route of each application <Cite c={C('T2_3')} /></h2><span className="small faint">APH Table 2.3 (Chapter II) and Chapter I for new institutions</span></div>
      <div className="tablewrap"><table className="t small"><thead><tr><th>Nature of application</th><th>Self-disclosure</th><th>Scrutiny / re-scrutiny</th><th>EVC</th><th>SAC / SHC</th><th>Security deposit</th></tr></thead>
        <tbody>{d.natures.map((n: any) => <tr key={n.id}><td>{n.label}{n.chapter === 'I' && <span className="faint"> (Chapter I) <Cite c={C('CL_1_4_2_B')} /></span>}</td>
          <td>{COL(n.route.includes('self_disclosure'))}</td><td>{COL(n.route.includes('scrutiny'))}</td><td>{COL(n.route.includes('evc'))}</td><td>{COL(n.aa.length ? 'AA' : false)}</td>
          <td>{n.deposit ? <span className="small">after approval</span> : <span className="faint">–</span>}</td></tr>)}</tbody></table></div></div>

    <div className="box"><div className="bh"><h2>Time allowed at each step</h2><span className="small faint">the handbook sets none; these drive reminders, escalation and the countdown</span></div>
      <div className="tablewrap"><table className="t small"><thead><tr><th>Stage</th><th>Held by</th><th className="num">Usual / allowed days</th><th className="num">Days to fix the meeting</th><th className="num">Notice (days)</th><th className="num">Report (days)</th><th>Clause</th></tr></thead>
        <tbody>{Object.entries(d.stages).map(([k, s]: any) => <tr key={k}><td>{s.label}</td><td>{s.schedule_by ? `${s.schedule_by === 'RB' ? 'Regulation Bureau' : 'Regional Office'} fixes, committee holds` : s.holder === 'institution' ? 'Institution' : s.holder === 'EC' ? 'Executive Committee' : 'Regulation Bureau'}</td>
          <td className="num"><Num k={`stages.${k}.days`} v={s.days} /></td><td className="num">{s.schedule_days !== undefined ? <Num k={`stages.${k}.schedule_days`} v={s.schedule_days} /> : '—'}</td>
          <td className="num">{s.lead !== undefined ? <Num k={`stages.${k}.lead`} v={s.lead} /> : '—'}</td><td className="num">{s.report !== undefined ? <Num k={`stages.${k}.report`} v={s.report} /> : '—'}</td>
          <td><Cite c={C(s.cite)} /></td></tr>)}</tbody></table></div></div>

    <div className="grid g2">
      <div className="box"><div className="bh"><h2>Academic Calendar for {d.cycle.ay}</h2><Cite c={C('CL_2_25_J')} /></div>
        <dl className="kv"><dt>Last date for approval</dt><dd>{admin ? <EditDate v={d.cycle.last_date_approval} onSave={(x) => save('cycle.last_date_approval', x)} /> : fmtDate(d.cycle.last_date_approval)}</dd>
          <dt>After appeal</dt><dd>{admin ? <EditDate v={d.cycle.last_date_after_appeal} onSave={(x) => save('cycle.last_date_after_appeal', x)} /> : fmtDate(d.cycle.last_date_after_appeal)}</dd>
          <dt>Executive Committee meets</dt><dd className="small">{d.cycle.ec_meetings.map(fmtDate).join(' · ')}</dd>
          <dt>Application windows</dt><dd className="small">{d.cycle.windows.map((w: any) => <div key={w.name}>{w.name}: {fmtDate(w.from)} to {fmtDate(w.to)}; committees from {fmtDate(w.scrutiny_from)}</div>)}</dd>
          <dt>Note</dt><dd className="small muted">{d.cycle.calendar_note}</dd></dl></div>
      <div className="box"><div className="bh"><h2>Reminders and escalation</h2></div>
        <dl className="kv">
          <dt>AICTE offices</dt><dd className="small">Reminder {d.alerts.aicte.due_soon_days} days before the time allowed runs out. Then: {d.alerts.aicte.ladder.map((l: any) => `${l.label} (after ${l.after} day${l.after === 1 ? '' : 's'}${l.spare_below !== undefined ? `, or at once if the calendar date is at stake` : ''}) to ${l.to}`).join('; ')}.</dd>
          <dt>Institutions</dt><dd className="small">Reminders {d.alerts.institution.remind_before.join(', ')} days before; overdue notices after {d.alerts.institution.overdue_notice_after.join(', ')} days; the processing officer is told after {d.alerts.institution.tell_officer_after} days. A late institution is never counted against an officer.</dd>
          <dt>Certificates</dt><dd className="small">Reminders {d.alerts.documents.remind_before.join(', ')} days before expiry; escalated {d.alerts.documents.escalate_after.join(' and ')} days after.</dd>
          <dt>Undertakings</dt><dd className="small">Reminders {d.alerts.undertakings.remind_before.join(', ')} days before; escalated {d.alerts.undertakings.escalate_after.join(' and ')} days after.</dd>
          <dt>Lease</dt><dd className="small">Reminders {d.alerts.lease.remind_before_months.join(', ')} months before the application window of the year the lease rule would block EoA <Cite c={C('CL_2_1_E')} /></dd>
          <dt>Channels</dt><dd className="small">Institutions: {d.alerts.channels.institution.join(', ')}. AICTE: {d.alerts.channels.aicte.join(', ')}.</dd></dl></div>
    </div>

    <div className="grid g2">
      <div className="box"><div className="bh"><h2>Certificates with a validity</h2></div>
        <table className="t small"><tbody>{Object.entries(d.documents).map(([k, x]: any) => <tr key={k}><td>{x.label}</td><td className="small">{x.valid_years ? `valid ${x.valid_years} years from issue` : x.min_years ? `at least ${x.min_years} years; lease rule applies` : 'as stated on the certificate'}{x.building_age ? `; needed once the building is ${x.building_age} years old` : ''}</td>
          <td>{x.verify_by === 'RO' ? 'Regional Office verifies' : 'Regulation Bureau verifies'}</td><td><Cite c={C(x.cite)} /></td></tr>)}</tbody></table></div>
      <div className="box"><div className="bh"><h2>Security deposit <Cite c={C(d.deposit.cite)} /></h2><Cite c={C(d.deposit.amounts_cite)} label="Table 1.4" /></div>
        <div className="bb small">Due within {d.deposit.days} days of intimation, with Affidavit 3. Then {d.deposit.steps.map((s: any) => `${s.penalty}% penalty up to ${s.until.split('-').reverse().join('/')}`).join(', ')}; after that: {d.deposit.after.toLowerCase()}.</div>
        <table className="t small"><thead><tr><th>Programme (Rs lakh)</th><th className="num">Diploma</th><th className="num">UG</th><th className="num">PG</th></tr></thead>
          <tbody>{Object.entries(d.deposit.amounts).map(([k, v]: any) => <tr key={k}><td>{k}</td>{v.map((x: number, i: number) => <td key={i} className="num">{x || '—'}</td>)}</tr>)}</tbody></table>
        <div className="bb small faint">Doubled for private leased land or building.</div></div>
    </div>

    <div className="box"><div className="bh"><h2>Conditions an approval can be granted subject to</h2><span className="small faint">each becomes a tracked item with a due date</span></div>
      <table className="t small"><tbody>{Object.entries(d.conditions).map(([k, c]: any) => <tr key={k}><td>{c.label}</td>
        <td className="small">{c.due_years ? `within ${c.due_years} year${c.due_years > 1 ? 's' : ''}` : c.due_months ? `within ${c.due_months} month${c.due_months > 1 ? 's' : ''}` : 'before the academic year starts'}{c.carry_forward ? '; carried into next year if unmet' : ''}</td>
        <td className="small muted">{c.consequence}</td><td><Cite c={C(c.cite)} /></td></tr>)}</tbody></table></div>

    {d.overrides.length > 0 && <div className="box"><div className="bh"><h2>Changes made</h2></div>
      <table className="t small"><thead><tr><th>Setting</th><th>New value</th><th>By</th><th>Reason</th></tr></thead>
        <tbody>{d.overrides.map((o: any) => <tr key={o.key}><td className="mono">{o.key}</td><td className="mono">{o.value}</td><td>{o.updated_by}</td><td>{o.reason}</td></tr>)}</tbody></table></div>}
  </div>
}

function EditNum({ v, onSave }: { v: number; onSave: (x: number) => void }) {
  const [x, setX] = useState(String(v))
  return <span className="row" style={{ justifyContent: 'flex-end', gap: 4 }}><input type="number" min={0} value={x} onChange={(e) => setX(e.target.value)} style={{ width: 62, padding: '2px 5px' }} />
    {Number(x) !== v && <button className="btn sm" onClick={() => onSave(Number(x))}>Save</button>}</span>
}

function EditDate({ v, onSave }: { v: string; onSave: (x: string) => void }) {
  const [x, setX] = useState(v)
  return <span className="row" style={{ gap: 4 }}><input type="date" value={x} onChange={(e) => setX(e.target.value)} />{x !== v && <button className="btn sm" onClick={() => onSave(x)}>Save</button>}</span>
}
