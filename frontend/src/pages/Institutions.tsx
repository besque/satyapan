import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { B } from '../ui'

export default function Institutions() {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<any[] | null>(null)
  useEffect(() => {
    const t = setTimeout(() => api(`/api/institutions?q=${encodeURIComponent(q)}`).then(setRows), q ? 250 : 0)
    return () => clearTimeout(t)
  }, [q])
  return (
    <div>
      <div className="titlebar">
        <div><h1>Institutions</h1><div className="sub">Each institution's complaints and actions across every bureau</div></div>
        <input placeholder="Name, city or Permanent ID (spelling need not be exact)" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 340 }} />
      </div>
      <div className="box"><div className="tablewrap"><table className="t cards">
        <thead><tr><th style={{ width: '36%' }}>Institution</th><th>Region</th><th>Open cases by bureau</th><th className="num">Coordination items</th><th className="num">All cases</th></tr></thead>
        <tbody>{rows?.map((r) => (
          <tr key={r.permanent_id} className="click" onClick={() => nav(`/institution/${r.permanent_id}`)}>
            <td><b>{r.name}</b><div className="small faint">{r.city}, {r.state} · {r.permanent_id} · {r.inst_type}</div></td>
            <td className="small">{r.region}</td>
            <td>{Object.entries(r.open_by_bureau).map(([b, n]: any) => <span key={b} style={{ marginRight: 6 }}><B b={b} /> {n}</span>)}
              {!r.open && <span className="faint small">None open</span>}</td>
            <td className="num">{r.alerts ? <span className="pill red">{r.alerts}</span> : <span className="faint">0</span>}</td>
            <td className="num">{r.total}</td>
          </tr>))}</tbody>
      </table></div>
        {rows && !rows.length && <div className="empty">No institution matches.</div>}</div>
    </div>
  )
}
