import { useEffect, useState } from 'react'
import { api } from '../api'
import { Tip } from '../ui'

const ACTION: Record<string, string> = {
  'auth.login': 'Signed in', 'case.received': 'Complaint received', 'case.accepted': 'Taken up', 'case.sought_reply': 'Reply sought from institution',
  'case.reply_received': 'Institution replied', 'case.inquiry_ordered': 'Inquiry / visit ordered', 'case.show_cause': 'Show-cause issued', 'case.hearing': 'Hearing held',
  'case.penal_action': 'Penal action recommended', 'case.eoa_processing': 'Approval under process', 'case.recommended_approval': 'Approval recommended',
  'case.transferred': 'Transferred', 'case.note': 'Note', 'case.escalated': 'Escalated (timeline)', 'case.linked': 'Cases linked',
  'case.disposed_resolved': 'Disposed: resolved', 'case.disposed_action_taken': 'Disposed: action taken', 'case.disposed_not_maintainable': 'Disposed: not maintainable',
  'case.disposed_merged': 'Disposed: merged', 'case.reopened': 'Reopened', 'case.viewed': 'Case viewed', 'case.category': 'Nature changed',
  'case.institution_confirmed': 'Institution confirmed', 'coordination.raised': 'Overlap alert raised', 'coordination.viewed': 'Overlap alert viewed',
  'coordination.ack': 'Overlap acknowledged', 'coordination.lead': 'Lead bureau set', 'coordination.resolve': 'Coordination closed', 'link.same': 'Marked same matter',
  'link.not_same': 'Marked not same matter', 'settings.changed': 'Setting changed', 'report.downloaded': 'Report downloaded', 'register.imported': 'Register imported',
  'register.previewed': 'Register checked', 'demo.seeded': 'Test data loaded',
}

export default function Audit() {
  const [d, setD] = useState<any>(null)
  const [q, setQ] = useState('')
  useEffect(() => { const t = setTimeout(() => api(`/api/audit?limit=400${q ? `&target=${encodeURIComponent(q)}` : ''}`).then(setD), 250); return () => clearTimeout(t) }, [q])
  return (
    <div>
      <div className="titlebar"><div><h1>Activity log <Tip>Every action, view, alert and setting change is recorded in order. Each entry carries a fingerprint of the one before it, so changing or deleting any past entry is detected.</Tip></h1>
        {d && <div className="sub">{d.chain.ok ? <span className="st green">Log intact</span> : <span className="st red">Log altered at entry {d.chain.broken_at}</span>} · {d.chain.entries} entries</div>}</div>
        <input placeholder="Filter by case no. or alert" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 280 }} /></div>
      <div className="box"><div className="tablewrap"><table className="t small">
        <thead><tr><th>#</th><th>Time</th><th>By</th><th>Action</th><th>On</th><th>Details</th></tr></thead>
        <tbody>{d?.entries.map((e: any) => <tr key={e.seq}><td className="faint">{e.seq}</td>
          <td style={{ whiteSpace: 'nowrap' }}>{new Date(e.ts).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })}</td>
          <td>{e.actor}</td><td>{ACTION[e.action] || e.action}</td><td className="mono">{e.target}</td>
          <td className="faint">{e.payload?.remarks || e.payload?.reason || e.payload?.note || (e.payload?.to ? `to ${e.payload.to}` : '')}</td></tr>)}</tbody>
      </table></div></div>
    </div>
  )
}
