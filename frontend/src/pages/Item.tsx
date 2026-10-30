import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, upload, withToken } from '../api'
import { useUser } from '../App'
import { Cite, fmtDate, fmtShort, Holder, InstLink, Loading, nameOf, Source, SplitBar } from '../ui'

export default function Item() {
  const { id } = useParams()
  const u = useUser()
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')
  const [valid, setValid] = useState('')
  const [reason, setReason] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const load = () => api(`/api/compliance/${id}`).then(setD).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [id])
  if (err && !d) return <div className="note bad">{err}</div>
  if (!d) return <Loading />
  const run = async (body: any) => {
    setBusy(true); setErr('')
    try { await api(`/api/compliance/${id}/act`, { method: 'POST', json: body }); await load(); setNote(''); setReason('') } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const needsDate = d.kind === 'document' || d.kind === 'lease'
  const ex = d.extra || {}
  return <div>
    <div className="crumbs"><Link to="/compliance">{u.role === 'institution' ? 'Undertakings and documents' : 'Compliance'}</Link> › {d.id}</div>
    <div className="titlebar"><div><h1>{d.title} <Source s={d.source} /></h1>
      <div className="sub">{d.kind_label} · {u.role !== 'institution' ? <InstLink pid={d.pid} name={d.institution} /> : nameOf(d.institution)}{d.app_id && <> · from <Link to={`/app/${d.app_id}`}>{d.app_id}</Link></>}</div></div>
      <span className={`pill ${d.state.color}`} style={{ fontSize: 14 }}>{d.state.label}</span></div>
    <div className="split">
      <div className="stack">
        <div className="box"><dl className="kv">
          {d.detail && <><dt>Details</dt><dd>{d.detail}</dd></>}
          <dt>Due</dt><dd>{fmtDate(d.due_on)}{d.opened_on && <span className="faint"> · opened {fmtDate(d.opened_on)}</span>}</dd>
          <dt>If not met</dt><dd>{d.consequence || '—'}</dd>
          <dt>Rule</dt><dd><Cite c={d.cite} /> {d.cite?.source === 'letter' && <span className="small faint">{d.cite.quote}</span>}</dd>
          <dt>With</dt><dd>{d.holder ? <Holder kind={d.holder.startsWith('INST:') ? 'institution' : 'aicte'} label={d.holder_label} /> : 'Closed'}</dd>
          {d.kind === 'deposit' && ex.amount_lakh && <><dt>Amount</dt><dd>Rs {ex.amount_lakh} lakh (Table 1.4) <Cite c={{ key: 'T1_4', ref: 'Table 1.4' }} />; intimated {fmtDate(ex.intimated_on)}</dd></>}
          {d.kind === 'lease' && ex.block && <><dt>Why</dt><dd>Lease ends {fmtDate(ex.block.lease_until)}. Longest course: {ex.block.max_years} years. At the start of {ex.block.blocked_ay} the live lease is {ex.block.live_years} years, so EoA cannot be issued from {ex.block.blocked_ay} unless the lease is extended by 30 years.</dd></>}
          {d.note && <><dt>Institution's note</dt><dd>{d.note}</dd></>}
          {d.evidence?.length > 0 && <><dt>Evidence</dt><dd>{d.evidence.map((f: string) => <a key={f} className="btn sm" href={withToken(`/api/files/${f}`)} target="_blank" rel="noreferrer">{f}</a>)}</dd></>}
          {d.source === 'public' && <><dt>Source</dt><dd><a href={d.source_url} target="_blank" rel="noreferrer">public copy of the letter</a>; {ex.real_status}</dd></>}
        </dl></div>
        {err && <div className="note bad">{err}</div>}
        {d.can.submit && <div className="box"><div className="bh"><h2>Submit evidence</h2></div><div className="bb"><div className="form">
          {needsDate && <label>{d.kind === 'lease' ? 'Lease now valid until' : 'Renewed certificate valid until'}<input type="date" value={valid} onChange={(e) => setValid(e.target.value)} /></label>}
          <label className={needsDate ? '' : 'full'}>Document<input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
          <label className="full">Note<textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <div className="full"><button className="btn primary" disabled={busy || (needsDate && !valid)} onClick={async () => {
            let files: string[] = []
            if (file) { const f = await upload(file); files = [f.id] }
            run({ action: 'submit', note, files, valid_until: valid || null })
          }}>Submit for verification</button></div></div></div></div>}
        {d.can.verify && <div className="box"><div className="bh"><h2>Verify</h2><span className="small faint">the institution's submission</span></div><div className="bb"><div className="form">
          <label className="full">Remarks (required to return)<textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          <div className="full row"><button className="btn primary" disabled={busy} onClick={() => run({ action: 'verify', reason })}>Verified</button>
            <button className="btn danger" disabled={busy || reason.length < 5} onClick={() => run({ action: 'return', reason })}>Return to institution</button></div></div></div></div>}
        {d.can.waive && <div className="box"><div className="bh"><h2>Waive (competent authority)</h2></div><div className="bb"><div className="form">
          <label className="full">Reason<textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          <div className="full"><button className="btn" disabled={busy || reason.length < 10} onClick={() => run({ action: 'waive', reason })}>Waive this condition</button></div></div></div></div>}
        <div className="box"><div className="bh"><h2>History</h2></div>
          <ol className="hist">{d.history.map((h: any) => <li key={h.id} className={h.kind}><span className="when">{fmtShort(h.on_date)}</span><span>{h.text}<span className="faint small"> · {h.actor}</span></span></li>)}</ol>
          {!d.history.length && <div className="empty">Read from the published letter.</div>}</div>
      </div>
      <div className="stack">
        {d.source === 'test' && <div className="box"><div className="bh"><h2>Who held it</h2></div><div className="bb"><SplitBar aicte={d.time.aicte} institution={d.time.institution} /></div></div>}
        <div className="box"><div className="bh"><h2>Reminders and escalations sent</h2></div>
          {d.alerts.map((x: any) => <div key={x.id} className="noterow" style={{ gridTemplateColumns: '58px 1fr' }}><span className="small faint">{fmtShort(x.on_date)}</span><span className="small">{x.text}</span></div>)}
          {!d.alerts.length && <div className="empty">None.</div>}</div>
      </div>
    </div>
  </div>
}
