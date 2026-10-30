import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { fmtDate, Loading, nameOf, Source } from '../ui'

export default function Institutions() {
  const nav = useNavigate()
  const [rows, setRows] = useState<any[] | null>(null)
  const [src, setSrc] = useState('')
  const [q, setQ] = useState('')
  useEffect(() => { api('/api/institutions').then(setRows) }, [])
  if (!rows) return <Loading />
  const shown = rows.filter((r) => (!src || r.source === src) && (!q || `${r.name} ${r.pid} ${r.city || ''} ${r.state || ''}`.toLowerCase().includes(q.toLowerCase())))
  return <div>
    <div className="titlebar"><div><h1>Institutions</h1><div className="sub">{rows.length} institutions · {rows.filter((r) => r.source === 'public').length} with published approval letters</div></div>
      <div className="row"><div className="seg">{[['', 'All'], ['test', 'Applying this cycle'], ['public', 'Published letters']].map(([k, l]) => <button key={k} className={src === k ? 'on' : ''} onClick={() => setSrc(k)}>{l}</button>)}</div>
        <input placeholder="Name, Permanent ID, city or state" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 260 }} /></div></div>
    <div className="box"><div className="tablewrap"><table className="t cards">
      <thead><tr><th>Institution</th><th>Region</th><th>Type</th><th className="num">Letters on record</th><th className="num">Applications</th><th className="num">Open items</th><th>Land</th></tr></thead>
      <tbody>{shown.map((r) => <tr key={r.pid} className="click" onClick={() => nav(`/institution/${r.pid}`)}>
        <td><b>{nameOf(r.name)}</b> <Source s={r.source} /><div className="small faint">{r.pid} · {r.city || r.state}</div></td>
        <td>{r.region}</td><td className="small">{r.inst_type}</td><td className="num">{r.letters}</td><td className="num">{r.applications}</td>
        <td className="num">{r.open_items}</td><td className="small">{r.land === 'lease' ? `Lease to ${fmtDate(r.lease_until)}` : r.land === 'own' ? 'Own' : '—'}</td></tr>)}</tbody>
    </table></div></div>
  </div>
}
