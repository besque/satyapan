import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useClock, useUser } from '../App'
import { AppLink, Cite, Counts, fmtDate, fmtShort, Loading, Modal, nameOf, Risk, Tip } from '../ui'

const GROUP: Record<string, string> = { to_schedule: 'Date to be fixed', awaiting_video: 'Video awaited from institution', scheduled: 'Fixed', report_due: 'Held, report to record', done: 'Done' }

export default function Evc() {
  const u = useUser()
  const nav = useNavigate()
  const [rows, setRows] = useState<any[] | null>(null)
  const [g, setG] = useState('to_schedule')
  const [pick, setPick] = useState<any>(null)
  const load = () => api('/api/evc').then(setRows)
  useEffect(() => { load() }, [])
  if (!rows) return <Loading />
  const n = (k: string) => rows.filter((r) => r.group === k).length
  const shown = rows.filter((r) => g === 'all' || r.group === g).sort((a, b) => (a.group === 'done' ? 1 : 0) - (b.group === 'done' ? 1 : 0) || (a.hold_by || 'z').localeCompare(b.hold_by || 'z'))
  return <div>
    <div className="titlebar"><div><h1>Expert Visit Committees <Tip>Applications enter this queue by themselves once scrutiny (and re-scrutiny) is complete and their route in APH Table 2.3 includes an EVC. The Regional Office fixes the date; members are picked by the portal's automated selection.</Tip></h1>
      <div className="sub">{u.role === 'ro' ? `${u.region} region` : 'All regions'} · constituted by the Regional Officer <Cite c={{ key: 'DEF_EVC', ref: 'Definition 29' }} /></div></div></div>
    <Counts on={g} set={setG} items={[
      { k: 'to_schedule', v: n('to_schedule'), l: 'Date to be fixed' },
      { k: 'awaiting_video', v: n('awaiting_video'), l: 'Video awaited' },
      { k: 'scheduled', v: n('scheduled'), l: 'Fixed' },
      { k: 'report_due', v: n('report_due'), l: 'Report to record', color: n('report_due') ? 'orange' : undefined },
      { k: 'done', v: n('done'), l: 'Done this cycle' },
      { k: 'all', v: rows.length, l: 'All' }]} />
    <div className="box"><div className="tablewrap"><table className="t cards">
      <thead><tr><th>Application</th><th>Stage</th><th>Waiting</th><th>Hold by <Tip>Latest date the EVC can be held for the application to be decided by the Academic Calendar date, counting back from the last Executive Committee meeting before it.</Tip></th><th>Against the calendar</th><th /></tr></thead>
      <tbody>{shown.map((r) => <tr key={`${r.app_id}-${r.attempt}-${r.opened_on}`} className="click" onClick={() => nav(`/app/${r.app_id}`)}>
        <td><AppLink id={r.app_id} /> <b>{nameOf(r.institution)}</b><div className="small faint">{r.nature_label} · {r.region}</div></td>
        <td>{GROUP[r.group]}{r.meeting_on && <div className="small faint">{r.mode} · {fmtShort(r.meeting_on)}</div>}{r.group === 'done' && <div className="small faint">{r.outcome} · {fmtShort(r.closed_on)}</div>}</td>
        <td>{r.waiting !== null ? <>{r.waiting} d{r.overdue > 0 && <div className="small" style={{ color: 'var(--red)' }}>{r.overdue} d past the time allowed</div>}</> : '—'}</td>
        <td>{r.hold_by ? fmtShort(r.hold_by) : '—'}</td>
        <td><Risk r={r.risk} spare={r.spare} /></td>
        <td onClick={(e) => e.stopPropagation()}>{r.can_schedule && r.group !== 'done' && <button className="btn sm primary" onClick={() => setPick(r)}>{r.group === 'to_schedule' ? 'Fix date' : 'Re-fix'}</button>}</td>
      </tr>)}</tbody></table></div>{!shown.length && <div className="empty">Nothing here.</div>}</div>
    {pick && <Schedule r={pick} onClose={() => setPick(null)} onDone={() => { setPick(null); load() }} />}
  </div>
}

function Schedule({ r, onClose, onDone }: { r: any; onClose: () => void; onDone: () => void }) {
  const { clock } = useClock()
  const plus = (iso: string, n: number) => { const x = new Date(iso + 'T00:00:00'); x.setDate(x.getDate() + n); return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}` }
  const [date, setDate] = useState(plus(clock!.today, 7))
  const [mode, setMode] = useState('online')
  const [err, setErr] = useState('')
  const late = r.hold_by && date > r.hold_by
  const go = async () => {
    try { await api(`/api/applications/${r.app_id}/act`, { method: 'POST', json: { action: 'schedule', meeting_on: date, mode } }); onDone() } catch (e: any) { setErr(e.message) }
  }
  return <Modal title={`Fix the EVC: ${nameOf(r.institution)}`} onClose={onClose}>
    <div className="form">
      <label>Date<input type="date" value={date} min={clock!.today} onChange={(e) => setDate(e.target.value)} /></label>
      <label>Mode<select value={mode} onChange={(e) => setMode(e.target.value)}><option value="online">Online</option><option value="physical">Physical visit</option></select></label>
      <div className="full small muted">Hold by {fmtDate(r.hold_by)} to stay on track. {mode === 'online' && 'The institution must upload a 30-minute facilities video two days before.'}</div>
      {late && <div className="full note bad">This date is after {fmtDate(r.hold_by)}: the application would then need fast-tracking, or miss the Academic Calendar date.</div>}
      {err && <div className="full note bad">{err}</div>}
      <div className="full"><button className="btn primary" onClick={go}>Fix this date and inform the institution</button></div>
    </div>
  </Modal>
}
