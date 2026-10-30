import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useUser } from '../App'
import { B, CaseLink, Due, Kind, KIND, Status, Tip, fmtDate, fmtTime } from '../ui'

export default function Coordination() {
  const { id } = useParams()
  return id ? <Detail id={id} /> : <List />
}

function List() {
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') || 'act'
  const [d, setD] = useState<any>(null)
  const [closed, setClosed] = useState<any[] | null>(null)
  useEffect(() => { api('/api/coordination').then(setD) }, [])
  useEffect(() => { if (tab === 'closed' && !closed) api('/api/coordination?status=closed').then((r) => setClosed(r.alerts)) }, [tab])
  const act = d?.alerts.filter((a: any) => a.kind !== 'parallel') || []
  const info = d?.alerts.filter((a: any) => a.kind === 'parallel') || []
  const rows = tab === 'act' ? act : tab === 'info' ? info : tab === 'closed' ? closed || [] : []
  return (
    <div>
      <div className="titlebar"><div><h1>Coordination</h1>
        <div className="sub">Where bureaus are, or may be, dealing with the same institution or the same matter</div></div></div>
      <div className="tabs">
        <button className={tab === 'act' ? 'on' : ''} onClick={() => setSp({ tab: 'act' })}>Needs coordination ({act.length})</button>
        <button className={tab === 'confirm' ? 'on' : ''} onClick={() => setSp({ tab: 'confirm' })}>Institution to confirm ({d?.unconfirmed.length ?? '…'})</button>
        <button className={tab === 'info' ? 'on' : ''} onClick={() => setSp({ tab: 'info' })}>For information ({info.length})</button>
        <button className={tab === 'closed' ? 'on' : ''} onClick={() => setSp({ tab: 'closed' })}>Closed</button>
      </div>
      {tab === 'act' && <div className="legend" style={{ marginBottom: 10 }}>
        {(['conflict', 'duplicate', 'pattern'] as const).map((k) => <span key={k}><Kind k={k} /> <Tip>{KIND[k].hint}</Tip></span>)}
      </div>}
      {tab !== 'confirm' ? <div className="box">
        {!d && <div className="empty"><span className="spinner" /></div>}
        {d && !rows.length && <div className="empty">Nothing here.</div>}
        <div className="tablewrap"><table className="t cards">
          {rows.length > 0 && <thead><tr><th>Kind</th><th style={{ width: '34%' }}>What</th><th>Institution</th><th>Bureaus</th><th>Lead</th><th>Response</th></tr></thead>}
          <tbody>{rows.map((a: any) => (
            <tr key={a.id} className="click" onClick={() => nav(`/coordination/${a.id}`)}>
              <td><Kind k={a.kind} /></td>
              <td><b>{a.title}</b><div className="small faint">{a.cases.length} cases · raised {fmtDate(a.created_at)}</div></td>
              <td>{a.institution}<div className="small faint">{a.region}</div></td>
              <td>{a.bureaus.map((b: string) => <B key={b} b={b} />)}</td>
              <td>{a.lead ? <B b={a.lead} /> : <span className="faint">—</span>}</td>
              <td className="small">{a.status === 'resolved' ? <span className="pill green">Closed</span> : a.status === 'cleared' ? <span className="pill grey">Cleared</span> :
                a.status === 'acknowledged' ? <span className="pill green">All acknowledged</span> :
                  <>{Object.keys(a.acks).length}/{a.bureaus.length} acknowledged</>}
                {a.closed_note && <div className="faint">{a.closed_note}</div>}</td>
            </tr>))}</tbody>
        </table></div>
      </div> : <div className="box">
        <div className="bh"><h2>Complaints not yet tied to an institution</h2><span className="small faint">overlaps can only be found once the institution is known</span></div>
        <div className="tablewrap"><table className="t cards">
          <thead><tr><th>Case</th><th>Written as</th><th>Best guess</th><th>Bureau</th></tr></thead>
          <tbody>{d?.unconfirmed.map((r: any) => (
            <tr key={r.id} className="click" onClick={() => nav(`/case/${r.id}`)}>
              <td><CaseLink id={r.id} /><div className="small faint">{fmtDate(r.received_on)}</div></td>
              <td>“{r.inst_text}”</td>
              <td className="small">{r.match?.candidates?.slice(0, 2).map((c: any) => <div key={c.permanent_id}>{c.name} <span className="faint">{Math.round(c.confidence * 100)}%</span></div>)}</td>
              <td><B b={r.bureau} /></td>
            </tr>))}</tbody>
        </table></div>
        {d && !d.unconfirmed.length && <div className="empty">All complaints are tied to an institution.</div>}
      </div>}
    </div>
  )
}

function Detail({ id }: { id: string }) {
  const u = useUser()
  const [d, setD] = useState<any>(null)
  const [note, setNote] = useState('')
  const [err, setErr] = useState('')
  const load = () => api(`/api/coordination/${id}`).then(setD)
  useEffect(() => { load() }, [id])
  if (!d) return <div className="empty"><span className="spinner" /></div>
  const post = async (what: string, body: any = {}) => {
    setErr('')
    try { await api(`/api/coordination/${id}/${what}`, { method: 'POST', json: { note, ...body } }); setNote(''); load() } catch (e: any) { setErr(e.message) }
  }
  const mine = u.bureau && d.bureaus.includes(u.bureau)
  const closed = d.status === 'resolved' || d.status === 'cleared'
  return (
    <div>
      <div className="crumbs"><Link to="/coordination">Coordination</Link> › {d.id}</div>
      <div className="titlebar"><div>
        <h1><Kind k={d.kind} /> {d.title}</h1>
        <div className="sub"><Link to={`/institution/${d.permanent_id}`}>{d.institution}</Link> · {d.region} Region · raised {fmtDate(d.created_at)}</div>
      </div></div>
      <div className="split">
        <div>
          <div className={`banner ${KIND[d.kind].color}`} style={{ cursor: 'default' }}><span><b>Why this was raised</b></span><span>{d.why}</span></div>
          <div className="box" style={{ marginBottom: 14 }}>
            <div className="bh"><h2>Evidence</h2></div>
            <ul className="why" style={{ padding: '10px 14px 10px 30px', margin: 0 }}>{d.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
          </div>
          <div className={`cmpcols n${Math.min(d.case_rows.length, 3)}`}>
            {d.case_rows.map((c: any) => (
              <div key={c.id} className="box cmp">
                <div className="bh"><span><CaseLink id={c.id} /> <B b={c.bureau} /></span><Status s={c.status} esc={c.esc_level} /></div>
                <div className="bb small">
                  <div><b>{c.category_label}</b> · {c.officer}</div>
                  <div className="faint">received {fmtDate(c.received_on)} · <Due t={c.timeline} /></div>
                  {c.description ? <div className="complaint sm">{c.description}</div> : <div className="faint" style={{ margin: '8px 0' }}>Text visible to {c.bureau}.</div>}
                  <ol className="hist sm">{c.history.map((h: any, i: number) => <li key={i}><span className="when">{fmtDate(h.ts)}</span><span className="what">{h.label}</span></li>)}</ol>
                </div>
              </div>))}
          </div>
        </div>
        <div className="grid sticky" style={{ gap: 14 }}>
          <div className="box">
            <div className="bh"><h2>Response</h2>{closed ? <span className="pill green">{d.status === 'cleared' ? 'Cleared' : 'Closed'}</span> : null}</div>
            <div className="bb">
              <div className="small muted" style={{ marginBottom: 6 }}>Suggested lead <Tip>The bureau best placed to act for all: the one that normally handles this nature of matter, or the one whose regulatory action should settle first.</Tip></div>
              <div style={{ marginBottom: 10 }}>{d.lead ? <><B b={d.lead} /> {d.bureau_names[d.lead]}</> : <span className="faint">No lead needed: for information</span>}</div>
              <div className="small muted" style={{ marginBottom: 6 }}>Acknowledged by</div>
              <div className="acks">{d.bureaus.map((b: string) => <div key={b} className={d.acks[b] ? 'ok' : ''}>
                <B b={b} /> {d.acks[b] ? <span className="small">{d.acks[b].by}, {fmtTime(d.acks[b].ts)}{d.acks[b].note ? `: “${d.acks[b].note}”` : ''}</span> : <span className="small faint">not yet</span>}</div>)}</div>
              {d.closed_note && <div className="note ok" style={{ marginTop: 10 }}>{d.closed_note}</div>}
              {!closed && d.can_respond && <div className="grid" style={{ gap: 8, marginTop: 12 }}>
                <textarea placeholder="Note (what your bureau will do)" value={note} onChange={(e) => setNote(e.target.value)} />
                {mine && !d.acks[u.bureau!] && <button className="btn primary" onClick={() => post('ack')}>Acknowledge for {u.bureau}</button>}
                {(u.role === 'management' || d.lead === u.bureau || !d.lead) &&
                  <button className="btn" disabled={!note.trim()} onClick={() => post('resolve')}>Close: coordination done</button>}
                <label className="small muted">Change lead
                  <select value={d.lead || ''} onChange={(e) => post('lead', { lead: e.target.value })} style={{ marginLeft: 6 }}>
                    <option value="" disabled>Choose…</option>
                    {Object.entries(d.bureau_names).map(([k, v]: any) => <option key={k} value={k}>{k} · {v}</option>)}
                  </select></label>
                {err && <div className="note bad">{err}</div>}
              </div>}
            </div>
          </div>
          <div className="box"><div className="bb small muted">The system only points out the overlap. Merging, transferring or closing a case is done by the officers on the case page, and every step is recorded.</div></div>
        </div>
      </div>
    </div>
  )
}
