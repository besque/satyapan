import { useEffect, useState } from 'react'
import { api } from '../api'
import { Tip } from '../ui'

const ACTION: Record<string, string> = {
  'application.received': 'Application received', 'application.processed': 'Checks completed', 'document.ingested': 'Document read',
  'rules.evaluated': 'Rules applied', 'verification.result': 'Issuer check', 'network.refreshed': 'Links updated', 'application.viewed': 'Viewed',
  'auth.login': 'Signed in', 'finding.confirmed': 'Problem confirmed', 'finding.dismissed': 'Problem dismissed', 'application.recommendation': 'Recommendation',
  'rule.changed': 'Rule changed', 'source.availability': 'Source switched', 'verification.resolved_manually': 'Issuer reply recorded',
  'verification.retried': 'Issuer check retried', 'eoa.verified': 'Letter checked', 'document.downloaded': 'File opened', 'application.rechecked': 'Re-checked',
  'demo.seeded': 'Test data loaded',
}

export default function Audit() {
  const [d, setD] = useState<any>(null)
  const [q, setQ] = useState('')
  useEffect(() => { api(`/api/audit?limit=400${q ? `&target=${encodeURIComponent(q)}` : ''}`).then(setD) }, [q])
  return (
    <div>
      <div className="titlebar"><div><h1>Activity log <Tip>Every action is recorded in order. Each entry is linked to the previous one by a fingerprint, so changing or deleting any old entry is detected.</Tip></h1>
        {d && <div className="sub">{d.chain.ok ? <span className="st green">Log intact</span> : <span className="st red">Log altered at entry {d.chain.broken_at}</span>} · {d.chain.entries} entries</div>}</div>
        <input placeholder="Filter by application or document ID" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 280 }} /></div>
      <div className="box"><div className="tablewrap"><table className="t small">
        <thead><tr><th>#</th><th>Time</th><th>By</th><th>Action</th><th>On</th></tr></thead>
        <tbody>{d?.entries.map((e: any) => <tr key={e.seq}><td className="faint">{e.seq}</td>
          <td style={{ whiteSpace: 'nowrap' }}>{new Date(e.ts).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'medium' })}</td>
          <td>{e.actor}</td><td>{ACTION[e.action] || e.action}</td><td className="mono">{e.target}</td></tr>)}</tbody>
      </table></div></div>
    </div>
  )
}
