import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useUser } from '../App'
import { docTitle, fmtDate, Modal, Result, Tip, titleCase } from '../ui'

const FILTERS: [string, string][] = [['source_unavailable', 'Source offline'], ['manual_review', 'Check by hand'], ['mismatch', 'Does not match'],
  ['expired', 'Expired'], ['verified', 'Confirmed'], ['all', 'All']]

export default function Verifications() {
  const user = useUser()
  const [rows, setRows] = useState<any[]>([])
  const [srcs, setSrcs] = useState<any[]>([])
  const [flt, setFlt] = useState('source_unavailable')
  const [open, setOpen] = useState<any>(null)
  const [st, setSt] = useState('verified')
  const [note, setNote] = useState('')
  const load = () => { api('/api/verifications').then(setRows); api('/api/sources').then(setSrcs) }
  useEffect(load, [])
  const shown = rows.filter((r) => flt === 'all' || r.status === flt)
  const resolve = async () => { await api(`/api/verifications/${open.id}/resolve`, { method: 'POST', json: { status: st, note } }); setOpen(null); setNote(''); load() }
  const toggle = async (s: any) => { await api(`/api/sources/${s.name}`, { method: 'PUT', json: { available: !s.available } }); load() }
  const retry = async (appId: string) => { await api(`/api/applications/${appId}/reverify`, { method: 'POST' }); setOpen(null); load() }
  return (
    <div>
      <div className="titlebar"><div><h1>Issuer checks <Tip>Each certificate is checked with the office that issued it. When that office's service is offline or not connected, the case waits here and a request letter is drafted for a person to send.</Tip></h1>
        <div className="sub">{rows.filter((r) => ['source_unavailable', 'manual_review'].includes(r.status)).length} waiting for a person</div></div></div>
      <div className="counts">
        {FILTERS.map(([k, l]) => <button key={k} className={flt === k ? 'on' : ''} onClick={() => setFlt(k)}>
          <span className="v">{k === 'all' ? rows.length : rows.filter((r) => r.status === k).length}</span><span className="l">{l}</span></button>)}
      </div>
      <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 320px' }}>
        <div className="box">
          <div className="tablewrap"><table className="t">
            <thead><tr><th>Institution</th><th>Document</th><th>Checked with</th><th>Result</th><th>Date</th></tr></thead>
            <tbody>{shown.map((r) => <tr key={r.id} className="click" onClick={() => setOpen(r)}>
              <td><Link to={`/app/${r.application_id}`} onClick={(e) => e.stopPropagation()}>{titleCase(r.name)}</Link></td>
              <td>{docTitle(r.doc_type)}</td><td className="small">{r.source}</td><td><Result s={r.status} /></td><td className="small faint">{fmtDate(r.ts)}</td></tr>)}</tbody>
          </table></div>
          {!shown.length && <div className="empty">Nothing here.</div>}
        </div>
        <div className="box">
          <div className="bh"><h3>Issuing offices</h3><Tip>Test sources stand in for state portals. “Not connected” means no online service is available, so documents are confirmed by letter.</Tip></div>
          <div className="tablewrap"><table className="t small"><tbody>{srcs.map((s) => <tr key={s.name}>
            <td>{s.label}</td>
            <td style={{ whiteSpace: 'nowrap' }}>{s.kind === 'not connected' ? <span className="pill grey">Not connected</span> : <span className={`pill ${s.available ? 'green' : 'red'}`}>{s.available ? 'Online' : 'Offline'}</span>}
              {user.role === 'admin' && s.kind !== 'not connected' && <div><button className="btn sm" style={{ marginTop: 4 }} onClick={() => toggle(s)}>{s.available ? 'Set offline' : 'Set online'}</button></div>}</td></tr>)}</tbody></table></div>
        </div>
      </div>
      {open && <Modal title={`${docTitle(open.doc_type)} · ${titleCase(open.name)}`} onClose={() => setOpen(null)}>
        <div className="row" style={{ marginBottom: 8 }}><Result s={open.status} /><span className="small muted">{open.source}</span></div>
        <p style={{ marginTop: 0 }}>{open.detail}</p>
        {open.checks?.length > 0 && <div className="tablewrap"><table className="t small" style={{ marginBottom: 10 }}><thead><tr><th>Field</th><th>On document</th><th>With issuer</th><th /></tr></thead>
          <tbody>{open.checks.map((c: any, i: number) => <tr key={i}><td>{c.field}</td><td>{String(c.document)}</td><td>{String(c.source)}</td><td>{c.match ? '✓' : '✗'}</td></tr>)}</tbody></table></div>}
        {open.letter && <details><summary>Letter to the issuing office</summary><pre className="calc">{open.letter}</pre>
          <button className="btn sm" onClick={() => navigator.clipboard?.writeText(open.letter)}>Copy</button></details>}
        {open.status === 'source_unavailable' && <div style={{ marginTop: 10 }}><button className="btn sm" onClick={() => retry(open.application_id)}>Try the source again</button></div>}
        {open.resolution && <div className="note" style={{ marginTop: 10 }}>Marked <b>{open.resolution.status}</b> by {open.resolution.by}: {open.resolution.note}</div>}
        {['verifier', 'admin'].includes(user.role) && <div className="box" style={{ marginTop: 12 }}>
          <div className="bh"><h3>Record the reply</h3></div>
          <div className="bb row">
            <select value={st} onChange={(e) => setSt(e.target.value)}>{[['verified', 'Confirmed'], ['mismatch', 'Does not match'], ['expired', 'Expired'], ['manual_review', 'Still checking']].map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            <input placeholder="How it was confirmed (letter no., date)" value={note} onChange={(e) => setNote(e.target.value)} style={{ flex: 1, minWidth: 220 }} />
            <button className="btn primary" disabled={note.trim().length < 5} onClick={resolve}>Save</button>
          </div>
        </div>}
      </Modal>}
    </div>
  )
}
