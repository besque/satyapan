import { useEffect, useState } from 'react'
import { api } from '../api'
import { fmtTime, Loading, Tip } from '../ui'

const ACTION: Record<string, string> = {
  'auth.login': 'Signed in', 'application.submitted': 'Application submitted', 'application.moved': 'Moved to stage', 'application.scheduled': 'Meeting fixed',
  'application.video': 'Video uploaded', 'application.outcome': 'Outcome recorded', 'application.compliance': 'Compliance submitted',
  'application.decision': 'Decision recorded', 'application.appeal': 'Appeal filed', 'application.lapsed': 'Appeal window lapsed',
  'application.reverted': 'Sent back', 'application.note': 'Note', 'application.escalated': 'Escalated', 'application.carried': 'Conditions carried forward',
  'application.viewed': 'Application viewed', 'compliance.created': 'Compliance item opened', 'compliance.submitted': 'Evidence submitted',
  'compliance.verified': 'Verified', 'compliance.returned': 'Returned to institution', 'compliance.waived': 'Waived', 'compliance.escalated': 'Escalated',
  'settings.changed': 'Rule changed', 'clock.moved': 'System date moved', 'letter.drafted': 'Letter drafted', 'report.downloaded': 'Report downloaded',
  'file.uploaded': 'File uploaded', 'demo.seeded': 'Sample data loaded',
}

export default function Audit() {
  const [d, setD] = useState<any>(null)
  const [q, setQ] = useState('')
  useEffect(() => { const t = setTimeout(() => api(`/api/audit?limit=400${q ? `&target=${encodeURIComponent(q.trim())}` : ''}`).then(setD), 250); return () => clearTimeout(t) }, [q])
  if (!d) return <Loading />
  return <div>
    <div className="titlebar"><div><h1>Activity log <Tip>Every movement, decision, submission, verification, escalation, rule change and view is recorded in order. Each entry carries the fingerprint (SHA-256) of the one before it, so changing or deleting any past entry is detected.</Tip></h1>
      <div className="sub">{d.chain.ok ? <span className="st green">Log intact</span> : <span className="st red">Log altered at entry {d.chain.broken_at}</span>} · {d.total} entries</div></div>
      <input placeholder="Filter by application or item no." value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 280 }} /></div>
    <div className="box"><div className="tablewrap"><table className="t small">
      <thead><tr><th>#</th><th>When</th><th>By</th><th>Action</th><th>On</th><th>Details</th><th>Fingerprint</th></tr></thead>
      <tbody>{d.rows.map((e: any) => <tr key={e.seq}><td className="faint">{e.seq}</td><td style={{ whiteSpace: 'nowrap' }}>{fmtTime(e.ts)}</td>
        <td>{e.actor}</td><td>{ACTION[e.action] || e.action}</td><td className="mono">{e.target}</td>
        <td className="faint">{e.payload?.text || e.payload?.reason || (e.payload?.to ? `to ${e.payload.to}` : '')}</td><td className="mono faint">{e.hash.slice(0, 10)}</td></tr>)}</tbody>
    </table></div></div>
  </div>
}
