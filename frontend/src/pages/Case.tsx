import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { B, CaseLink, Due, Kind, KIND, Marked, Meter, Modal, Status, Tip, fmtDate, fmtTime } from '../ui'

export default function Case() {
  const id = useParams()['*'] || ''
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState('')
  const load = () => api(`/api/cases/${id}/detail`).then(setD).catch((e) => setErr(e.message))
  useEffect(() => { setD(null); load() }, [id])
  if (err) return <div className="note bad">{err}</div>
  if (!d) return <div className="empty"><span className="spinner" /> Loading…</div>
  const inst = d.institution_detail
  return (
    <div>
      <div className="crumbs"><Link to="/cases">Cases</Link> › {d.id}</div>
      <div className="titlebar">
        <div>
          <h1><span className="mono" style={{ fontSize: 19 }}>{d.id}</span> <Status s={d.status} esc={d.esc_level} /></h1>
          <div className="sub"><B b={d.bureau} /> {d.officer} · received {fmtDate(d.received_on)} via {d.source}{d.ext_ref ? ` (${d.ext_ref})` : ''}</div>
        </div>
        <div style={{ minWidth: 220 }}><Due t={d.timeline} /><div><Meter t={d.timeline} /></div>
          <div className="small faint">{d.status === 'disposed' ? d.outcome : `Timeline ${d.timeline.total} days (${d.category_label})`}</div></div>
      </div>

      {d.coordination.length > 0 && <div style={{ marginBottom: 14 }}>
        {d.coordination.map((a: any) => (
          <Link key={a.id} to={`/coordination/${a.id}`} className={`banner ${KIND[a.kind].color}`}>
            <span><Kind k={a.kind} /> <b>{a.title}</b> <span className="small">· {a.bureaus.join(', ')}{a.lead ? ` · lead suggested: ${a.lead}` : ''}</span></span>
            <span className="small">{a.why}</span>
          </Link>))}
      </div>}

      <div className="split">
        <div className="grid" style={{ gap: 14 }}>
          <div className="box">
            <div className="bh"><h2>Complaint</h2><span className="small faint">{d.lang === 'hi' ? 'Hindi' : 'English'} · {d.complainant_type === 'Institution' ? 'From the institution' : `${d.complainant_type}: ${d.complainant || '—'}`}</span></div>
            <div className="bb">
              {d.visible ? <>
                <h3 style={{ marginBottom: 6 }}>{d.subject}</h3>
                <Marked text={d.description} spans={d.spans} />
                {d.spans.length > 0 && <div className="small faint" style={{ marginTop: 6 }}>Marked: what the system used. Click a mark to see why.</div>}
              </> : <div className="note">Complaint text is visible to the handling bureau ({d.bureau}) and to bureaus that share a coordination item on it. <Tip>Complainant details and text are kept within the bureau that handles the case. Other bureaus see who is handling it, its status and its actions.</Tip></div>}
            </div>
          </div>

          <InstitutionBox d={d} reload={load} />
          <NatureBox d={d} reload={load} />

          <div className="box">
            <div className="bh"><h2>Other cases on {inst ? inst.name : 'this institution'}</h2>
              {inst && <Link to={`/institution/${inst.permanent_id}`} className="small">Institution timeline →</Link>}</div>
            {!d.related.length && <div className="empty">No other cases on this institution.</div>}
            {d.related.map((r: any) => <Related key={r.id} me={d} r={r} reload={load} />)}
          </div>

          <div className="box">
            <div className="bh"><h2>History</h2><span className="small faint">every step, with who and when</span></div>
            <ol className="hist">{d.history.map((h: any) => (
              <li key={h.id} className={h.kind}>
                <span className="when">{fmtTime(h.ts)}</span>
                <span className="what"><b>{h.label}</b>{h.to_bureau ? <> → <B b={h.to_bureau} /></> : null} <span className="faint">· {h.actor}{h.bureau ? ` (${h.bureau})` : ''}</span>
                  {h.remarks && <div className="small muted">{h.remarks}</div>}
                  {h.extra?.warnings_seen?.length > 0 && <div className="small" style={{ color: 'var(--red)' }}>Went ahead despite coordination check ({h.extra.warnings_seen.join(', ')}): {h.extra.reason}</div>}
                </span>
              </li>))}</ol>
          </div>
        </div>

        <div className="grid sticky" style={{ gap: 14 }}>
          <div className="box">
            <div className="bh"><h2>Tracking</h2></div>
            <dl className="kv">
              <dt>Handled by</dt><dd><B b={d.bureau} /> {d.bureaus.find((b: any) => b.id === d.bureau)?.name}</dd>
              <dt>Officer</dt><dd>{d.officer || '—'}</dd>
              <dt>Nature</dt><dd>{d.category_label}</dd>
              <dt>Status</dt><dd><Status s={d.status} esc={d.esc_level} /></dd>
              <dt>Last action</dt><dd>{d.last_action}<div className="small faint">{fmtDate(d.last_action_on)}</div></dd>
              <dt>Next action</dt><dd>{d.next_action || '—'}{d.next_due && <div className="small faint">by {fmtDate(d.next_due)}</div>}</dd>
              <dt>Expected disposal</dt><dd>{fmtDate(d.due_on)}</dd>
              {d.disposed_on && <><dt>Disposed</dt><dd>{fmtDate(d.disposed_on)} · {d.outcome}</dd></>}
            </dl>
          </div>
          {d.can_act && <ActionBox d={d} reload={load} />}
        </div>
      </div>
    </div>
  )
}

function InstitutionBox({ d, reload }: { d: any; reload: () => void }) {
  const inst = d.institution_detail
  const m = d.match || {}
  const [busy, setBusy] = useState(false)
  const pick = async (pid: string | null) => {
    setBusy(true)
    try { await api(`/api/cases/${d.id}/institution`, { method: 'POST', json: { permanent_id: pid } }); reload() } finally { setBusy(false) }
  }
  const open = d.match_state === 'confirm' || d.match_state === 'unmatched'
  const top = m.candidates?.[0]
  return (
    <div className={`box ${open ? 'attn' : ''}`}>
      <div className="bh"><h2>Institution</h2>
        <span className="small faint">{d.match_state === 'confirmed' ? 'confirmed by an officer' : d.match_state === 'auto' ? `identified automatically (${Math.round((m.confidence || 0) * 100)}%)` : d.match_state === 'not_aicte' ? 'not an AICTE institution' : 'needs confirmation'}</span></div>
      <div className="bb">
        <div className="small muted" style={{ marginBottom: 6 }}>Written by the complainant as: <Marked text={d.inst_text} spans={d.inst_spans} /></div>
        {inst && !open && <div>
          <Link to={`/institution/${inst.permanent_id}`}><b>{inst.name}</b></Link> <span className="small faint">· {inst.city}, {inst.state} · {inst.region} Region · {inst.permanent_id}</span>
          {d.match_state === 'auto' && top && top.permanent_id === inst.permanent_id && <ul className="why">{top.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>}
        </div>}
        {open && <>
          <div className="note" style={{ marginBottom: 8 }}>{d.match_state === 'unmatched' ? 'No AICTE institution matches this closely.' : 'More than one institution could be meant.'} Choose the right one.</div>
          {(m.candidates || []).map((c: any) => (
            <div key={c.permanent_id} className="cand">
              <div><b>{c.name}</b> <span className="small faint">{c.city}, {c.state} · {c.permanent_id}</span>
                <ul className="why">{c.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></div>
              <div className="row"><span className="small faint">{Math.round(c.confidence * 100)}%</span>
                {d.can_act && <button className="btn sm primary" disabled={busy} onClick={() => pick(c.permanent_id)}>This one</button>}</div>
            </div>))}
          {d.can_act && <button className="btn sm" disabled={busy} onClick={() => pick(null)}>Not an AICTE institution</button>}
        </>}
      </div>
    </div>
  )
}

function NatureBox({ d, reload }: { d: any; reload: () => void }) {
  const [edit, setEdit] = useState(false)
  const save = async (c: string) => { await api(`/api/cases/${d.id}/category`, { method: 'POST', json: { category: c } }); setEdit(false); reload() }
  const ai = d.category_ai || []
  return (
    <div className="box">
      <div className="bh"><h2>Nature of complaint <Tip>Suggested by a multilingual language model that runs on this server: the complaint is compared with a plain description of each category (Settings). The officer can change it.</Tip></h2>
        {d.can_act && <button className="btn sm" onClick={() => setEdit(!edit)}>{edit ? 'Cancel' : 'Change'}</button>}</div>
      <div className="bb">
        <b>{d.category_label}</b>
        {ai.length > 0 && <div className="small faint" style={{ marginTop: 4 }}>Model's reading: {ai.map((a: any) => `${a.label} ${Math.round(a.score * 100)}%`).join(' · ')}</div>}
        {d.suggested_bureau && d.suggested_bureau !== d.bureau && d.status !== 'disposed' &&
          <div className="note" style={{ marginTop: 8 }}>Complaints of this nature are normally handled by <B b={d.suggested_bureau} />. Use <i>Transfer</i> if it should move.</div>}
        {edit && <div className="row" style={{ marginTop: 8 }}>
          <select defaultValue={d.category} onChange={(e) => save(e.target.value)}>
            {d.categories.map((c: any) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select></div>}
      </div>
    </div>
  )
}

function Related({ me, r, reload }: { me: any; r: any; reload: () => void }) {
  const [busy, setBusy] = useState(false)
  const link = async (kind: string) => {
    setBusy(true)
    try { await api('/api/links', { method: 'POST', json: { a: me.id, b: r.id, kind } }); reload() } finally { setBusy(false) }
  }
  const mayLink = me.can_act && r.status !== 'disposed'
  return (
    <div className={`rel ${r.same ? 'same' : ''}`}>
      <div className="spread">
        <span><CaseLink id={r.id} /> <B b={r.bureau} /> <Status s={r.status} esc={r.esc_level} /> <span className="small faint">{r.category_label} · {fmtDate(r.received_on)}</span></span>
        {r.same ? <span className="pill orange">Same matter? {Math.round(r.score * 100)}%</span> : <span className="small faint">{Math.round(r.score * 100)}%</span>}
      </div>
      <div className="small">{r.subject || <span className="faint">({r.bureau} case; text with {r.bureau})</span>} · <span className="faint">{r.last_action}, {fmtDate(r.last_action_on)}</span></div>
      {r.same && <ul className="why">{r.reasons.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>}
      {mayLink && <div className="row" style={{ marginTop: 4 }}>
        {!r.same && <button className="btn sm" disabled={busy} onClick={() => link('same')}>Same matter</button>}
        {r.same && <button className="btn sm" disabled={busy} onClick={() => link('not_same')}>Not the same matter</button>}
      </div>}
    </div>
  )
}

function ActionBox({ d, reload }: { d: any; reload: () => void }) {
  const [kind, setKind] = useState(d.status === 'pending' ? 'accepted' : 'sought_reply')
  const [remarks, setRemarks] = useState('')
  const [to, setTo] = useState('')
  const [warn, setWarn] = useState<any[] | null>(null)
  const [reason, setReason] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<any[]>([])
  useEffect(() => {
    setPreview([])
    if (kind === 'note') return
    api(`/api/cases/${d.id}/precheck`, { method: 'POST', json: { kind } }).then((r) => setPreview(r.warnings)).catch(() => {})
  }, [kind, d.id])
  const send = async (ack = false) => {
    setErr(''); setBusy(true)
    try {
      await api(`/api/cases/${d.id}/action`, { method: 'POST', json: { kind, remarks, acknowledged: ack, reason, to_bureau: kind === 'transferred' ? to : null } })
      setWarn(null); setRemarks(''); setReason(''); reload()
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 409) setWarn(e.body.warnings)
      else setErr(e.message)
    } finally { setBusy(false) }
  }
  const opts = [...d.actions, { kind: 'transferred', label: 'Transfer to another bureau' }]
  return (
    <div className="box">
      <div className="bh"><h2>Record an action</h2></div>
      <div className="bb grid" style={{ gap: 8 }}>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {opts.map((a: any) => <option key={a.kind} value={a.kind}>{a.label}</option>)}
        </select>
        {kind === 'transferred' && <select value={to} onChange={(e) => setTo(e.target.value)}>
          <option value="">Transfer to…</option>
          {d.bureaus.filter((b: any) => b.id !== d.bureau).map((b: any) => <option key={b.id} value={b.id}>{b.id} · {b.name}{b.id === d.suggested_bureau ? ' (suggested)' : ''}</option>)}
        </select>}
        <textarea placeholder="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} />
        {preview.length > 0 && <div className="note bad small">Before you act: {preview.length} item{preview.length > 1 ? 's' : ''} from other bureaus to look at.</div>}
        <button className="btn primary" disabled={busy || (kind === 'transferred' && !to)} onClick={() => send(false)}>Save action</button>
        {err && <div className="note bad">{err}</div>}
      </div>
      {warn && <Modal title="Before you act" onClose={() => setWarn(null)}>
        <p className="muted" style={{ marginTop: 0 }}>Other bureaus are acting on the same institution. Check with them first, or record why you are going ahead.</p>
        {warn.map((w: any, i: number) => (
          <div key={i} className={`warnbox ${w.severity}`}>
            <b>{w.title}</b>
            <div className="small"><CaseLink id={w.case} /> <B b={w.bureau} />: {w.their_action}{w.their_on ? `, ${fmtDate(w.their_on)}` : ''}</div>
            <div className="small muted">{w.why}</div>
          </div>))}
        <label className="small" style={{ display: 'block', marginTop: 10 }}>Reason for going ahead (recorded in the case and the activity log)</label>
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Spoke to RB; they agree this reply is needed for the grievance" />
        <div className="row" style={{ marginTop: 10, justifyContent: 'flex-end' }}>
          <button className="btn" onClick={() => setWarn(null)}>Stop and coordinate</button>
          <button className="btn danger" disabled={!reason.trim() || busy} onClick={() => send(true)}>Go ahead and record reason</button>
        </div>
      </Modal>}
    </div>
  )
}
