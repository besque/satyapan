import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useParams } from 'react-router-dom'
import { api, upload } from '../api'
import { useBrand, useClock, useUser } from '../App'
import { Cite, days, Due, fmtDate, fmtShort, Holder, InstLink, Loading, Modal, nameOf, PathBar, RISK, RouteStrip, Source, SplitBar, Tip } from '../ui'

const LETTERS: [string, string][] = [['summary', 'Case summary'], ['deficiency', 'Deficiency letter'], ['evc', 'EVC intimation'], ['decision', 'Decision letter'], ['escalation', 'Escalation note']]
const RESULT: Record<string, string> = { in_order: 'Found in order', deficient: 'Deficiencies found', recommend: 'Recommend', not_recommend: 'Do not recommend', fresh_evc: 'Order a fresh EVC' }

export default function Application() {
  const { id } = useParams()
  const u = useUser()
  const { clock } = useClock()
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState('')
  const [letter, setLetter] = useState<string | null>(null)
  useEffect(() => { setD(null); api(`/api/applications/${id}`).then(setD).catch((e) => setErr(e.message)) }, [id])
  if (err) return <div className="note bad">{err}</div>
  if (!d) return <Loading />
  const a = d.app, inst = d.institution, cd = d.countdown
  const act = async (body: any) => { const r = await api(`/api/applications/${id}/act`, { method: 'POST', json: body }); setD(r) }
  const dt = a.detail || {}
  return <div>
    <div className="crumbs"><Link to={u.role === 'institution' ? '/' : '/applications'}>{u.role === 'institution' ? 'What you owe AICTE' : 'Applications'}</Link> › {a.id}</div>
    <div className="titlebar">
      <div><h1>{nameOf(inst.name)} <Source s={inst.source} /></h1>
        <div className="sub">{a.id} · {a.nature_label}{dt.course ? ` (${dt.course}${dt.from ? `, ${dt.from} → ${dt.to}` : ''})` : ''} · {inst.region} region · Permanent ID {inst.pid} · submitted {fmtDate(a.submitted_on)}</div></div>
      <div className="row noprint">{LETTERS.filter(([k]) => !(u.role === 'institution' && k === 'escalation')).map(([k, l]) => <button key={k} className="btn sm" onClick={() => setLetter(k)}>{l}</button>)}</div>
    </div>

    <div className="box"><div className="bh"><h2>Route <Tip>The stages this nature of application goes through, exactly as APH Table 2.3: “Yes” stages always, “AA” stages only if the previous step finds deficiencies. The application moves to the next stage automatically when a stage is recorded as complete.</Tip></h2>
      <span className="row small faint">Table 2.3: Scrutiny {d.route.table.scrutiny} · EVC {d.route.table.evc} · SAC/SHC {d.route.table.sac_shc}{d.route.chapter === 'I' ? ' · Chapter I (new institution)' : ''} <Cite c={{ key: 'T2_3', ref: 'Table 2.3' }} /></span></div>
      <div className="bb"><RouteStrip chips={d.route.chips} />
        <div className="legend" style={{ marginTop: 8 }}><span><i className="sw done" />done</span><span><i className="sw cur" />now</span><span><i className="sw next" />still to come</span><span><i className="sw maybe" />only if needed</span></div></div></div>

    <div className="split" style={{ marginTop: 14 }}>
      <div className="stack">
        {cd ? <div className="box"><div className="bh"><h2>Against the Academic Calendar <Tip>Counted back from the last date for {cd.deadline_kind === 'approval' ? 'grant of approval' : 'decisions after appeal'}: each remaining stage takes its usual time (set on the Rules page), and the Executive Committee only meets on its fixed dates. So the system knows the latest date by which this step must finish.</Tip></h2>
          <Cite c={{ key: 'CL_2_25_J', ref: 'Cl. 2.25 (j)' }} /></div>
          <div className="bb">
            <div className="bigrisk"><span className={`n ${RISK[cd.risk].color}`}>{RISK[cd.risk].word}</span>
              <span className="muted">{cd.risk === 'will_miss' ? `${-cd.spare_fast} days short even if fast-tracked` : cd.spare >= 0 ? `${cd.spare} days to spare` : `${-cd.spare} days short at the usual pace`}</span></div>
            <p className="small" style={{ margin: '8px 0 0' }}>{cd.why}</p>
            {clock && <PathBar cd={cd} today={clock.today} />}
            <dl className="kv" style={{ padding: '10px 0 0' }}>
              <dt>Last date</dt><dd>{fmtDate(cd.deadline)} ({cd.deadline_kind === 'approval' ? 'grant of approval' : 'after appeal'})</dd>
              <dt>This step must finish by</dt><dd><b>{fmtDate(cd.finish_by)}</b>{cd.finish_by_fast !== cd.finish_by && <span className="faint"> (by {fmtDate(cd.finish_by_fast)} at the latest, if what follows is fast-tracked)</span>}</dd>
              {cd.hold_by && <><dt>Hold the committee by</dt><dd>{fmtDate(cd.hold_by)}{cd.schedule_by && <span className="faint">; fix the date by {fmtDate(cd.schedule_by)} to give notice</span>}</dd></>}
              <dt>Still to come</dt><dd>{cd.path.length ? cd.path.map((s: string) => d.route.chips.find((c: any) => c.stage === s)?.label || s).join(' → ') : 'Nothing: this is the last step'}</dd>
            </dl>
          </div></div>
          : <div className="box"><div className="bb"><span className={`st ${a.status === 'approved' ? 'green' : 'orange'}`}>{a.status_label}</span> {a.decided_on && <span className="muted">on {fmtDate(a.decided_on)}</span>}</div></div>}

        {d.step && <Now d={d} />}
        {Object.keys(d.actions).length > 0 && <Actions d={d} act={act} />}

        {(a.deficiencies.length > 0 || a.carried.length > 0) && <div className="box"><div className="bh"><h2>Deficiencies</h2></div><div className="bb">
          {a.deficiencies.length > 0 && <><div className="small faint">Open on this application</div><ul className="defs">{a.deficiencies.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></>}
          {a.carried.length > 0 && <div style={{ marginTop: 8 }}><div className="small faint">Carried from the previous approval <Tip>Conditions of last year's approval that were still open when this application came in are carried into it automatically: APH Cl. 2.25 (c) requires them to be met before the next EoA. They close when a committee finds the application in order.</Tip></div>
            <ul className="defs">{a.carried.map((c: any) => <li key={c.item_id}><span className="carried">carried</span> {c.title}{c.detail ? `: ${c.detail}` : ''} <span className="faint">(due {fmtDate(c.due_on)})</span> · <Link to={`/item/${c.item_id}`}>{c.status_label}</Link></li>)}</ul></div>}
        </div></div>}

        <div className="box"><div className="bh"><h2>Stages so far</h2></div><div className="tablewrap"><table className="t small">
          <thead><tr><th>Stage</th><th>Opened</th><th>Closed</th><th>Outcome</th><th>Days</th></tr></thead>
          <tbody>{d.steps.map((s: any) => <tr key={s.id}><td>{s.label}{s.attempt > 1 ? ` (round ${s.attempt})` : ''}{s.meeting_on && <div className="faint">{s.mode} · {fmtShort(s.meeting_on)}</div>}</td>
            <td>{fmtShort(s.opened_on)}</td><td>{s.closed_on ? fmtShort(s.closed_on) : <i className="faint">open</i>}</td>
            <td>{s.outcome_label}{s.deficiencies.length > 0 && <div className="faint">{s.deficiencies.join('; ')}</div>}{s.remarks && <div className="faint">{s.remarks}</div>}</td>
            <td className="num">{s.closed_on ? days(s.opened_on, s.closed_on) : '—'}</td></tr>)}</tbody></table></div></div>

        <div className="box"><div className="bh"><h2>History</h2><span className="small faint">every movement, with who and when; also in the activity log</span></div>
          <ol className="hist">{d.history.map((h: any) => <li key={h.id} className={h.kind}><span className="when">{fmtShort(h.on_date)}</span>
            <span>{h.text}<span className="faint small"> · {h.actor}</span></span></li>)}</ol></div>
      </div>

      <div className="stack">
        <div className="box"><div className="bh"><h2>Who held the ball</h2></div><div className="bb"><SplitBar aicte={d.time.aicte} institution={d.time.institution} />
          <table className="t small" style={{ marginTop: 8 }}><tbody>{d.time.by.map((x: any) => <tr key={x.holder}><td><Holder kind={x.kind} label={x.label} /></td><td className="num">{x.days} d</td></tr>)}</tbody></table></div></div>
        <div className="box"><div className="bh"><h2>Institution</h2>{u.role !== 'institution' && <InstLink pid={inst.pid} name="Open" />}</div>
          <dl className="kv"><dt>Type</dt><dd>{inst.inst_type}</dd><dt>Trust / society</dt><dd>{inst.trust}</dd><dt>Land</dt><dd>{inst.land === 'lease' ? `Leased, until ${fmtDate(inst.lease_until)}` : 'Own'}</dd>
            <dt>Longest course</dt><dd>{inst.max_years} years</dd></dl></div>
        {d.items.length > 0 && <div className="box"><div className="bh"><h2>Undertakings and documents</h2></div>
          {d.items.slice(0, 8).map((i: any) => <Link key={i.id} to={`/item/${i.id}`} className="noterow" style={{ gridTemplateColumns: '1fr auto' }}>
            <span className="small"><b>{i.title}</b>{i.detail && <div className="faint">{i.detail}</div>}</span><span className={`pill ${i.state.color}`}>{i.state.label}</span></Link>)}</div>}
        {d.letters.length > 0 && <div className="box"><div className="bh"><h2>Approval letters on record</h2></div>
          <table className="t small"><tbody>{d.letters.map((l: any) => <tr key={l.id}><td>{l.ay}</td><td>{fmtShort(l.issued_on)}</td>
            <td>{l.deficiencies.length ? <span className="pill orange">{l.deficiencies.length} deficiencies noted</span> : <span className="faint">none noted</span>}</td></tr>)}</tbody></table></div>}
        <div className="box"><div className="bh"><h2>Messages sent</h2><Link className="small" to="/alerts">All</Link></div>
          {d.alerts.slice(0, 8).map((x: any) => <div key={x.id} className="noterow" style={{ gridTemplateColumns: '58px 1fr' }}><span className="small faint">{fmtShort(x.on_date)}</span><span className="small">{x.text}</span></div>)}
          {!d.alerts.length && <div className="empty">None yet.</div>}</div>
      </div>
    </div>
    {letter && <LetterModal appId={a.id} kind={letter} onClose={() => setLetter(null)} />}
  </div>
}

function Now({ d }: { d: any }) {
  const s = d.step, a = d.app
  return <div className="box"><div className="bh"><h2>Now: {a.task}</h2><Cite c={s.cite} /></div>
    <dl className="kv">
      <dt>With</dt><dd><Holder kind={a.holder_kind} label={a.holder_label} days={a.with_days} /></dd>
      <dt>Time allowed</dt><dd>until {fmtDate(s.due_on)} · <Due due={a.due_on} overdue={a.overdue} left={a.days_left} />{a.esc_level >= 1 && <span className="small" style={{ color: 'var(--red)' }}> · {a.esc_level >= 3 ? 'escalated to senior management' : a.esc_level >= 2 ? 'escalated to head of office' : 'overdue notice sent'}</span>}</dd>
      {s.meeting_on && <><dt>Meeting</dt><dd>{fmtDate(s.meeting_on)} · {s.mode}</dd></>}
      {s.members?.length > 0 && <><dt>Members</dt><dd className="small">{s.members.map((m: any) => `${m.name} (${m.role})`).join('; ')} <span className="faint">· picked by the portal's automated selection</span></dd></>}
      {s.extra?.video && <><dt>Facilities video</dt><dd className="small">uploaded {fmtDate(s.extra.video.on)} · <a href={s.extra.video.link} target="_blank" rel="noreferrer">link</a></dd></>}
      {s.extra?.clarification && <><dt>Clarification sought</dt><dd className="small">{s.extra.clarification}</dd></>}
      {s.stage === 'compliance' && a.deficiencies.length > 0 && <><dt>To comply</dt><dd><ul className="defs" style={{ marginTop: 0 }}>{a.deficiencies.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></dd></>}
    </dl></div>
}

function Actions({ d, act }: { d: any; act: (b: any) => Promise<void> }) {
  const A = d.actions, s = d.step, cd = d.countdown, a = d.app
  const { clock } = useClock()
  const today = clock?.today || ''
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const run = async (body: any) => { setBusy(true); setErr(''); try { await act(body) } catch (e: any) { setErr(e.message) } finally { setBusy(false) } }
  const lead = A.schedule?.lead || 7
  const plus = (iso: string, n: number) => { const x = new Date(iso + 'T00:00:00'); x.setDate(x.getDate() + n); return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}` }
  const [meeting, setMeeting] = useState(today ? plus(today, lead) : '')
  const [mode, setMode] = useState('online')
  const [result, setResult] = useState(A.outcome?.options[0] || '')
  const prefill = (s?.stage === 're_scrutiny' || s?.stage === 'shc') ? a.deficiencies : a.carried.filter((c: any) => ['open', 'rejected'].includes(c.status)).map((c: any) => `${c.detail || c.title} (carried from the previous approval)`)
  const [defs, setDefs] = useState<string>(prefill.join('\n'))
  const [remarks, setRemarks] = useState('')
  const [link, setLink] = useState('')
  const [decision, setDecision] = useState('approve')
  const [conds, setConds] = useState<string[]>((A.decide?.suggest || []).map((c: any) => c.key))
  const [to, setTo] = useState(A.revert?.targets[0]?.stage || '')
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [file, setFile] = useState<File | null>(null)
  // warn before fixing a date that is too late for the calendar
  const report = 2
  const late = meeting && cd ? (plus(meeting, report) > cd.finish_by_fast ? 'miss' : plus(meeting, report) > cd.finish_by ? 'fast' : '') : ''
  return <div className="box actions"><div className="bh"><h2>What you can do</h2><span className="small faint">recorded in the history and the activity log</span></div>
    {err && <div className="bb"><div className="note bad">{err}</div></div>}
    {A.schedule && <div className="bb">
      <h3 style={{ marginBottom: 6 }}>{s.phase === 'to_schedule' ? `Fix the date of the ${s.label}` : `Re-fix the date of the ${s.label}`}</h3>
      <div className="form">
        <label>Meeting date<input type="date" value={meeting} min={today} onChange={(e) => setMeeting(e.target.value)} /></label>
        <label>Mode<select value={mode} onChange={(e) => setMode(e.target.value)}><option value="online">Online</option><option value="physical">Physical visit</option></select></label>
        <div className="full small muted">{cd?.hold_by && <>To stay on track, hold it by <b>{fmtDate(cd.hold_by)}</b>. </>}Give at least {lead} days' notice. Members are picked by the portal's automated selection (Cl. 1.8 a, 1.9 a).
          {s.stage === 'evc' && mode === 'online' && ' For an online EVC the institution must upload a facilities video of at least 30 minutes two days before (Cl. 1.9 f).'}</div>
        {late && <div className="full note bad">{late === 'miss' ? `This date is too late: even if everything after it is fast-tracked, the decision would come after ${fmtDate(cd.deadline)}. Pick a date on or before ${fmtDate(plus(cd.finish_by_fast, -report))}.`
          : `With this date, everything after it must be fast-tracked to make ${fmtDate(cd.deadline)}. On or before ${fmtDate(plus(cd.finish_by, -report))} keeps the usual pace.`}</div>}
        <div className="full"><button className="btn primary" disabled={busy || !meeting} onClick={() => run({ action: 'schedule', meeting_on: meeting, mode })}>Fix this date and inform the institution</button></div>
      </div></div>}
    {A.outcome && <div className="bb">
      <h3 style={{ marginBottom: 6 }}>Record the outcome of the {s.label}</h3>
      <div className="form">
        <label className="full">Outcome<div className="seg">{A.outcome.options.map((o: string) => <button key={o} className={result === o ? 'on' : ''} onClick={() => setResult(o)}>{RESULT[o]}</button>)}</div></label>
        {result === 'deficient' && <label className="full">Deficiencies, one per line{prefill.length > 0 && <span className="faint"> (pre-filled: {s.stage === 're_scrutiny' || s.stage === 'shc' ? 'the deficiencies to be verified' : 'conditions carried from last year'})</span>}
          <textarea rows={4} value={defs} onChange={(e) => setDefs(e.target.value)} /></label>}
        <label className="full">Remarks<textarea rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} /></label>
        <div className="full small muted">The application then moves on by itself: {result === 'deficient' ? (s.stage === 'scrutiny' || s.stage === 'self_disclosure' ? 'to the institution for compliance, then re-scrutiny.' : 'to the next applicable stage (Table 2.3).') : 'to the next stage of its route.'}</div>
        <div className="full"><button className="btn primary" disabled={busy} onClick={() => run({ action: 'outcome', result, deficiencies: result === 'deficient' ? defs.split('\n') : [], remarks })}>Record outcome</button></div>
      </div></div>}
    {A.video && <div className="bb"><h3 style={{ marginBottom: 6 }}>Share the facilities video for the online EVC</h3>
      <div className="form"><label className="full">Link to the video on your website (at least 30 minutes; Cl. 1.9 f)<input value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://" /></label>
        <div className="full"><button className="btn primary" disabled={busy || link.length < 8} onClick={() => run({ action: 'video', link })}>Submit link</button></div></div></div>}
    {A.comply && <div className="bb"><h3 style={{ marginBottom: 6 }}>Submit compliance</h3>
      <div className="form"><label className="full">What you have done<textarea rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} /></label>
        <label className="full">Supporting document (optional)<input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
        <div className="full"><button className="btn primary" disabled={busy || remarks.length < 5} onClick={async () => {
          let files: string[] = []
          if (file) { const f = await upload(file); files = [f.id] }
          run({ action: 'comply', remarks, files })
        }}>Submit compliance</button></div></div></div>}
    {A.appeal && <div className="bb"><h3 style={{ marginBottom: 6 }}>Appeal (once, within 7 days)</h3>
      <div className="form"><label className="full">Grounds and compliance<textarea rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} /></label>
        <div className="full"><button className="btn primary" disabled={busy || remarks.length < 5} onClick={() => run({ action: 'appeal', remarks })}>File appeal</button></div></div></div>}
    {A.decide && <div className="bb"><h3 style={{ marginBottom: 6 }}>Record the decision of the {s.stage === 'ec' ? 'Executive Committee' : 'Council'}</h3>
      <div className="form">
        <label className="full">Decision<div className="seg">{[['approve', 'Approve'], ['lod', 'Letter of Deficiency'], ['reject', 'Reject']].map(([k, l]) => <button key={k} className={decision === k ? 'on' : ''} onClick={() => setDecision(k)}>{l}</button>)}</div></label>
        {decision === 'approve' && <div className="full checks"><div className="small faint">Approval subject to (each becomes a tracked item with a due date; ticked ones are suggested by the system)</div>
          {A.decide.conditions.map((c: any) => { const sg = A.decide.suggest.find((x: any) => x.key === c.key)
            return <label key={c.key}><input type="checkbox" checked={conds.includes(c.key)} onChange={(e) => setConds(e.target.checked ? [...conds, c.key] : conds.filter((x) => x !== c.key))} />
              <span>{c.label}{sg && <span className="faint"> · suggested: {sg.why}</span>}</span></label> })}</div>}
        <label className="full">Remarks / reasons<textarea rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} /></label>
        <div className="full small muted">This records the decision taken by the competent authority. The system never decides.</div>
        <div className="full"><button className="btn primary" disabled={busy} onClick={() => run({ action: 'decide', decision, remarks,
          conditions: decision === 'approve' ? conds.map((k) => ({ key: k, detail: A.decide.suggest.find((x: any) => x.key === k)?.detail || '' })) : [] })}>Record decision</button></div>
      </div></div>}
    {A.revert && <div className="bb"><h3 style={{ marginBottom: 6 }}>Return or send back</h3>
      <div className="form"><label>Send to<select value={to} onChange={(e) => setTo(e.target.value)}>{A.revert.targets.map((t: any) => <option key={t.stage} value={t.stage}>{t.label}</option>)}</select></label>
        <label className="full">Reason (recorded and shown to the institution where relevant)<textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <div className="full"><button className="btn" disabled={busy || reason.length < 10} onClick={() => run({ action: 'revert', to, reason })}>Send back</button></div></div></div>}
    {A.note && <div className="bb"><div className="form"><label className="full">Note on the file<textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></label>
      <div className="full"><button className="btn sm" disabled={busy || !note.trim()} onClick={() => { run({ action: 'note', text: note }); setNote('') }}>Add note</button></div></div></div>}
  </div>
}

export function LetterModal({ appId, kind, onClose }: { appId: string; kind: string; onClose: () => void }) {
  const brand = useBrand()
  const [l, setL] = useState<any>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api(`/api/applications/${appId}/letter/${kind}`).then(setL).catch((e) => setErr(e.message)) }, [appId, kind])
  const print = () => { document.body.classList.add('print-letter'); window.print(); setTimeout(() => document.body.classList.remove('print-letter'), 500) }
  const body = l && <div className="letter">
    <div className="lh"><span>{l.ref}</span><span className="draft">DRAFT · NOT ISSUED</span><span>{l.date}</span></div>
    {l.to && <p>To,<br />{l.to}</p>}
    <h3>{l.subject}</h3>
    {l.facts && <table><tbody>{l.facts.map(([k, v]: string[]) => <tr key={k}><th style={{ width: 160 }}>{k}</th><td>{v}</td></tr>)}</tbody></table>}
    {l.table && <table><thead><tr>{l.table.head.map((h: string) => <th key={h}>{h}</th>)}</tr></thead><tbody>{l.table.rows.map((r: string[], i: number) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table>}
    {l.lists?.map(([h, xs]: [string, string[]]) => <div key={h}><b>{h}</b><ul>{xs.map((x, i) => <li key={i}>{x}</li>)}</ul></div>)}
    {l.paras?.filter(Boolean).map((p: string, i: number) => <p key={i}>{p}</p>)}
    {l.points?.filter(Boolean).length > 0 && <ol>{l.points.filter(Boolean).map((p: string, i: number) => <li key={i}>{p}</li>)}</ol>}
    {l.after?.filter(Boolean).map((p: string, i: number) => <p key={i}>{p}</p>)}
    <div className="foot-l">Drafted by {brand.name} from the record of {l.ref}. It is sent only after an authorised officer reviews it.</div>
  </div>
  return <>
    <Modal title={l?.title || 'Letter'} onClose={onClose} wide actions={l && <button className="btn sm primary" onClick={print}>Print</button>}>
      {err ? <div className="note bad">{err}</div> : !l ? <Loading /> : body}
    </Modal>
    {l && createPortal(<div className="print-area">{body}</div>, document.body)}
  </>
}
