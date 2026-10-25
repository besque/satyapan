import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useUser } from '../App'
import { fmtDate, Lane, titleCase } from '../ui'

export default function MyApplications() {
  const user = useUser()
  const nav = useNavigate()
  const [apps, setApps] = useState<any[]>([])
  useEffect(() => { api('/api/applications').then((x) => setApps(x.sort((a: any, b: any) => (b.processed_at || '').localeCompare(a.processed_at || '')))) }, [])
  return (
    <div>
      <div className="titlebar"><div><h1>{titleCase(user.name)}</h1><div className="sub">Your applications and checks</div></div>
        <button className="btn primary" onClick={() => nav('/precheck')}>Check before submitting</button></div>
      <div className="box"><table className="t">
        <thead><tr><th>Date</th><th>Type</th><th>Status</th><th>Problems</th><th /></tr></thead>
        <tbody>{apps.map((a) => <tr key={a.id} className="click" onClick={() => nav(`/app/${a.id}`)}>
          <td>{fmtDate(a.processed_at)}</td><td>{a.source === 'precheck' ? 'Self-check' : 'Application'}</td>
          <td><Lane lane={a.lane} /></td><td>{a.n_fail || 'None'}</td><td><button className="btn sm">View</button></td></tr>)}</tbody>
      </table></div>
    </div>
  )
}
