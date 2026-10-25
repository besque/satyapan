import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Lane, LANE, Tip, titleCase } from '../ui'

export default function Dashboard() {
  const nav = useNavigate()
  const [apps, setApps] = useState<any[]>([])
  const [flt, setFlt] = useState('all')
  const [q, setQ] = useState('')
  useEffect(() => { api('/api/applications').then(setApps) }, [])
  const count = (l: string) => apps.filter((a) => a.lane === l).length
  const order: Record<string, number> = { red: 0, amber: 1, green: 2 }
  const shown = apps
    .filter((a) => flt === 'all' || (flt === 'real' ? a.source === 'public' : a.lane === flt))
    .filter((a) => !q || (a.name + a.permanent_id + a.state).toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => (order[a.lane] ?? 3) - (order[b.lane] ?? 3) || (b.n_fail - a.n_fail))
  return (
    <div>
      <div className="titlebar">
        <div><h1>Applications</h1><div className="sub">Extension of Approval 2027-28</div></div>
        <input placeholder="Search by name, ID or state" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 280 }} />
      </div>
      <div className="counts">
        <button className={flt === 'all' ? 'on' : ''} onClick={() => setFlt('all')}><span className="v">{apps.length}</span><span className="l">All applications</span></button>
        {(['red', 'amber', 'green'] as const).map((l) => (
          <button key={l} className={flt === l ? 'on' : ''} onClick={() => setFlt(l)}>
            <span className="v" style={{ color: `var(--${LANE[l].color})` }}>{count(l)}</span>
            <span className="l"><Lane lane={l} /> <Tip>{LANE[l].hint}</Tip></span>
          </button>
        ))}
        <button className={flt === 'real' ? 'on' : ''} onClick={() => setFlt('real')}><span className="v">{apps.filter((a) => a.source === 'public').length}</span>
          <span className="l">Real institutions <Tip>Checked using only the documents these colleges publish on their own websites.</Tip></span></button>
      </div>
      <div className="box">
        <div className="tablewrap"><table className="t cards">
          <thead><tr><th style={{ width: '34%' }}>Institution</th><th>State</th><th>Status</th><th>Main problems</th><th /></tr></thead>
          <tbody>
            {shown.map((a) => (
              <tr key={a.id} className="click" onClick={() => nav(`/app/${a.id}`)}>
                <td>
                  <a href={`/app/${a.id}`} onClick={(e) => e.preventDefault()}><b>{titleCase(a.name)}</b></a>
                  <div className="small faint">{a.permanent_id} {a.source === 'public' ? <span className="pill real">Real · public documents</span> : <span className="pill test">Test data</span>}</div>
                </td>
                <td className="hide-sm">{a.state}</td>
                <td><Lane lane={a.lane} /></td>
                <td className="small">
                  {a.top.length ? a.top.map((t: any, i: number) => <div key={i}>• {t.title}</div>) : <span className="faint">{a.n_check ? `${a.n_check} item(s) to check` : 'None'}</span>}
                  {a.n_fail > a.top.length && <div className="faint">+ {a.n_fail - a.top.length} more</div>}
                </td>
                <td className="hide-sm"><button className="btn sm">View</button></td>
              </tr>
            ))}
          </tbody>
        </table></div>
        {!shown.length && <div className="empty">No applications.</div>}
      </div>
    </div>
  )
}
