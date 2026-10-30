import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useUser } from '../App'
import { Cite, Counts, fmtDate, Holder, Loading, nameOf, Source, Tip } from '../ui'

const KINDS: [string, string][] = [['', 'All'], ['undertaking', 'Undertakings'], ['document', 'Certificates'], ['lease', 'Lease'], ['deposit', 'Security deposits']]

export default function Compliance() {
  const u = useUser()
  const nav = useNavigate()
  const [rows, setRows] = useState<any[] | null>(null)
  const qs = new URLSearchParams(window.location.search)
  const [kind, setKind] = useState(qs.get('kind') || '')
  const [src, setSrc] = useState(qs.get('src') === 'public' ? 'public' : 'test')
  const [state, setState] = useState('open')
  const [q, setQ] = useState('')
  useEffect(() => { api('/api/compliance').then(setRows) }, [])
  if (!rows) return <Loading />
  const inst = u.role === 'institution'
  const base = rows.filter((r) => (!kind || r.kind === kind) && (inst || r.source === src)
    && (!q || `${r.institution} ${r.title} ${r.detail || ''} ${r.pid}`.toLowerCase().includes(q.toLowerCase())))
  const isOpen = (r: any) => ['open', 'submitted', 'rejected'].includes(r.status)
  const pick = (r: any) => state === 'all' || (state === 'open' ? isOpen(r) : state === 'late' ? r.state.color === 'red' && isOpen(r)
    : state === 'soon' ? ['due_soon', 'due'].includes(r.state.key) : state === 'verify' ? r.status === 'submitted' : state === 'closed' ? !isOpen(r) : true)
  const shown = src === 'public' && !inst ? base : base.filter(pick)
  return <div>
    <div className="titlebar"><div><h1>{inst ? 'Undertakings and documents' : 'Compliance after approval'} <Tip>Every condition an approval was granted subject to, every certificate with an expiry date, lease extensions and security deposits. Each item has one holder at a time: the institution until it submits evidence, then the verifying office.</Tip></h1>
      <div className="sub">{inst ? 'What you have undertaken to AICTE, and its state' : 'Reminders go out before each due date; late items are escalated to the verifying office'}</div></div>
      <input placeholder="Search institution or item" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 260 }} /></div>
    <div className="row" style={{ marginBottom: 12 }}>
      <div className="seg">{KINDS.map(([k, l]) => <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>{l}</button>)}</div>
      {!inst && <div className="seg"><button className={src === 'test' ? 'on' : ''} onClick={() => setSrc('test')}>This cycle</button>
        <button className={src === 'public' ? 'on' : ''} onClick={() => setSrc('public')}>From published approval letters</button></div>}
    </div>
    {src === 'public' && !inst ? <RealNote rows={base} /> :
      <Counts on={state} set={setState} items={[
        { k: 'open', v: base.filter(isOpen).length, l: 'Open' },
        { k: 'late', v: base.filter((r) => r.state.color === 'red' && isOpen(r)).length, l: 'Overdue or expired', color: 'red' },
        { k: 'soon', v: base.filter((r) => ['due_soon', 'due'].includes(r.state.key)).length, l: 'Due within 30 days', color: 'orange' },
        { k: 'verify', v: base.filter((r) => r.status === 'submitted').length, l: 'Submitted, to verify', color: 'blue' },
        { k: 'closed', v: base.filter((r) => !isOpen(r)).length, l: 'Verified or closed', color: 'green' },
        { k: 'all', v: base.length, l: 'All' }]} />}
    <div className="box"><div className="tablewrap"><table className="t cards">
      <thead><tr><th>Item</th>{!inst && <th>Institution</th>}<th>Due</th><th>State</th><th>With</th><th>Rule</th></tr></thead>
      <tbody>{shown.map((r) => <tr key={r.id} className={r.source === 'test' ? 'click' : ''} onClick={() => r.source === 'test' && nav(`/item/${r.id}`)}>
        <td><b>{r.title}</b><div className="small faint">{r.kind_label}{r.detail ? ` · ${r.detail}` : ''}</div>
          {r.source === 'public' && <div className="small"><Source s="public" /> {r.source_url && <a href={r.source_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>letter</a>}
            {r.extra?.comply_within && <span className="faint"> · letter says: comply within {r.extra.comply_within}</span>}</div>}</td>
        {!inst && <td>{nameOf(r.institution)}<div className="small faint">{r.region}</div></td>}
        <td>{fmtDate(r.due_on)}</td>
        <td><span className={`pill ${r.state.color}`}>{r.state.label}</span></td>
        <td>{r.source === 'test' && r.holder ? <Holder kind={r.holder.startsWith('INST:') ? 'institution' : 'aicte'} label={r.holder.startsWith('INST:') ? (inst ? 'You' : 'Institution') : r.holder_label} /> : <span className="faint">—</span>}</td>
        <td onClick={(e) => e.stopPropagation()}><Cite c={r.cite} /></td>
      </tr>)}</tbody></table></div>{!shown.length && <div className="empty">Nothing here.</div>}</div>
  </div>
}

function RealNote({ rows }: { rows: any[] }) {
  const again = rows.filter((r) => r.state.label.startsWith('Noted again')).length
  const cleared = rows.filter((r) => r.state.label.startsWith('Not noted')).length
  return <div className="note info" style={{ marginBottom: 14 }}>
    <b>{rows.length} approvals granted subject to deficiencies</b>, read from Extension of Approval letters that institutions have published.
    Each letter states its own time limit (most say “shall be complied within Six Months from the date of issue of this EoA”; some say one year),
    so each becomes an undertaking with a due date. Where the next year's letter is also published, <b>{again}</b> had the same deficiency noted again
    and <b>{cleared}</b> did not.
  </div>
}
