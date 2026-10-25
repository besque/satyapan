import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { useUser } from '../App'
import { ClauseModal, DocWithMarks, docTitle, fmtDate, inr, Lane, Result, resultColor, Tip, titleCase, type Mark } from '../ui'

const FIELD_NAMES: Record<string, string> = {
  noc_no: 'Certificate no.', issue_date: 'Date of issue', valid_until: 'Valid up to', premises: 'Premises', address: 'Address', occupancy: 'Occupancy type',
  authority: 'Issued by', cert_no: 'Certificate no.', owner: 'Owner', built_up_area: 'Built-up area (sq.m)', floors: 'Floors', estamp_cert_no: 'e-Stamp no.',
  estamp_date: 'e-Stamp date', stamp_value: 'Stamp value (Rs.)', first_party: 'First party', deponent: 'Deponent', trust_name: 'Trust', institution_name: 'Institution',
  application_no: 'Application no.', notary_name: 'Notary', notary_reg_no: 'Notary reg. no.', sworn_date: 'Sworn on', txn_id: 'Transaction ID', amount: 'Amount (Rs.)',
  payment_date: 'Paid on', permanent_id: 'Permanent ID', status: 'Payment status', engineer: 'Engineer', engineer_reg_no: 'Engineer reg. no.',
  construction_year: 'Year of construction', udin: 'UDIN', frn: 'Firm reg. no.', membership_no: 'Membership no.', signed_date: 'Signed on', latlon: 'Coordinates',
}

const niceValue = (v: any) => /^\d{4}-\d{2}-\d{2}$/.test(String(v))
  ? new Date(String(v)).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : String(v)

function evidenceMarks(f: any, docId: string): Mark[] {
  return (f.evidence || []).filter((e: any) => e.doc_id === docId).map((e: any, i: number) => ({
    key: `${f.id}-${i}`, page: e.page || 0, bbox: e.bbox, title: f.title, note: String(e.label || '').replace(/\d{4}-\d{2}-\d{2}/g, (m: string) => niceValue(m)), color: resultColor(f.status) === 'green' ? 'green' : f.kind === 'network' ? 'violet' : resultColor(f.status),
    body: <FindingBody f={f} />,
  }))
}

function FindingBody({ f, onRule }: { f: any; onRule?: (c: any) => void }) {
  return <>
    <div>{f.detail}</div>
    {f.remedy && f.status !== 'pass' && <><div className="k">What fixes it</div><div>{f.remedy}</div></>}
    {f.derivation && <details style={{ marginTop: 8 }}><summary className="small">How the requirement was worked out</summary><div className="calc">{f.derivation.join('\n')}</div></details>}
    {f.citation?.ref && <div className="k">Rule: {f.citation.ref} {onRule && f.citation.loc && <button className="btn sm" style={{ marginLeft: 6 }} onClick={() => onRule(f.citation)}>Open in handbook</button>}</div>}
  </>
}

function Review({ f, onDone }: { f: any; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const [err, setErr] = useState('')
  const go = async (decision: string) => {
    try { await api(`/api/findings/${f.id}/review`, { method: 'POST', json: { decision, reason } }); setReason(''); onDone() }
    catch (e: any) { setErr(e.message) }
  }
  if (f.review) return <div className="small" style={{ marginTop: 8 }}>{f.review.decision === 'confirm' ? 'Confirmed' : 'Dismissed'} by {f.review.actor}: “{f.review.reason}”</div>
  return <div style={{ marginTop: 10 }}>
    <input placeholder="Your remark (required)" value={reason} onChange={(e) => setReason(e.target.value)} style={{ width: '100%' }} />
    <div className="row" style={{ marginTop: 6 }}>
      <button className="btn sm danger" disabled={reason.trim().length < 5} onClick={() => go('confirm')}>Confirm problem</button>
      <button className="btn sm" disabled={reason.trim().length < 5} onClick={() => go('dismiss')}>Not a problem</button>
      {err && <span className="small" style={{ color: 'var(--red)' }}>{err}</span>}
    </div>
  </div>
}

export default function Application() {
  const { id, docId } = useParams()
  const user = useUser()
  const [d, setD] = useState<any>(null)
  const [tab, setTab] = useState(docId ? 'docs' : 'problems')
  const [open, setOpen] = useState<string | null>(null)
  const [docSel, setDocSel] = useState<string | null>(docId || null)
  const [markSel, setMarkSel] = useState<string | null>(null)
  const [showPassed, setShowPassed] = useState(false)
  const [cite, setCite] = useState<any>(null)
  const load = () => api(`/api/applications/${id}`).then(setD)
  useEffect(() => { setD(null); load() }, [id])
  useEffect(() => { if (docId) { setDocSel(docId); setTab('docs') } }, [docId])

  const findings = d?.findings || []
  const docs = d?.documents || []
  const groups = useMemo(() => ({
    fail: findings.filter((f: any) => f.status === 'fail'),
    check: findings.filter((f: any) => (f.status === 'warn' || f.status === 'manual') && f.severity !== 'low'),
    notes: findings.filter((f: any) => (f.status === 'warn' || f.status === 'manual') && f.severity === 'low'),
    pass: findings.filter((f: any) => f.status === 'pass'),
    na: findings.filter((f: any) => f.status === 'na'),
  }), [findings])
  if (!d) return <div className="empty"><span className="spinner" /> Loading…</div>
  const a = d.application
  const staff = user.role !== 'institution'
  const isPublic = a.source === 'public'
  const doc = docs.find((x: any) => x.id === docSel) || docs.find((x: any) => x.doc_type !== 'infra_photo') || docs[0]

  const showOnDoc = (f: any) => {
    const e = (f.evidence || []).find((x: any) => x.doc_id && x.bbox) || (f.evidence || []).find((x: any) => x.doc_id)
    if (!e) return
    setDocSel(e.doc_id); setMarkSel(`${f.id}-${(f.evidence || []).filter((x: any) => x.doc_id === e.doc_id).indexOf(e)}`); setTab('docs')
  }
  const docMarks = (dc: any): Mark[] => {
    if (!dc) return []
    const ms: Mark[] = []
    findings.filter((f: any) => f.status !== 'pass' && f.status !== 'na').forEach((f: any) => ms.push(...evidenceMarks(f, dc.id)))
    Object.entries(dc.extraction || {}).forEach(([k, v]: [string, any]) => {
      const dup = ms.some((m) => m.bbox && v?.bbox && m.page === (v.page || 0) && Math.abs(m.bbox[0] - v.bbox[0]) < 2 && Math.abs(m.bbox[1] - v.bbox[1]) < 2)
      if (v && v.bbox && FIELD_NAMES[k] && !dup) ms.push({ key: 'fld-' + k, page: v.page || 0, bbox: v.bbox, title: FIELD_NAMES[k], color: 'grey',
        note: niceValue(v.value ?? v.raw ?? (v.lat ? `${v.lat}, ${v.lon}` : '')), body: <div className="small">Read from the document{v.raw && v.raw !== String(v.value) ? `: “${v.raw}”` : ''}.</div> })
    })
    return ms
  }

  const Item = ({ f, n }: { f: any; n: number }) => {
    const on = open === f.id
    const hasDoc = (f.evidence || []).some((e: any) => e.doc_id)
    const onDocName = docs.find((x: any) => (f.evidence || []).some((e: any) => e.doc_id === x.id))
    return <div>
      <div className={`issue ${on ? 'sel' : ''}`} role="button" tabIndex={0} aria-expanded={on}
        onClick={() => setOpen(on ? null : f.id)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(on ? null : f.id) } }}>
        <span className={`n ${f.kind === 'network' && f.status === 'fail' ? 'violet' : resultColor(f.status)}`}>{n}</span>
        <span className="t1">{f.title}</span>
        <span className="side small faint">{onDocName ? docTitle(onDocName.doc_type) : f.kind === 'network' ? 'Other institutions' : 'Application'}<span className="chev">›</span></span>
      </div>
      {on && <div className="detail">
        <FindingBody f={f} onRule={setCite} />
        <div className="row" style={{ marginTop: 10 }}>
          {hasDoc && <button className="btn sm primary" onClick={() => showOnDoc(f)}>Show on document</button>}
          {f.kind === 'network' && <Link className="btn sm" to="/network">See the link</Link>}
          {(f.evidence || []).filter((e: any) => e.application_id && e.application_id !== a.id).slice(0, 1).map((e: any) =>
            <Link key="o" className="btn sm" to={`/app/${e.application_id}`}>Open other institution</Link>)}
        </div>
        {staff && user.role !== 'verifier' && f.status !== 'pass' && <Review f={f} onDone={load} />}
      </div>}
    </div>
  }

  return (
    <div>
      <div className="crumbs"><Link to={staff ? '/' : '/my'}>{staff ? 'Applications' : 'My applications'}</Link> › {titleCase(d.institution?.name || d.form.institution_name)}</div>
      <div className="titlebar">
        <div>
          <h1>{titleCase(d.institution?.name || d.form.institution_name)}</h1>
          <div className="sub">Permanent ID {a.permanent_id} · {d.institution?.state} · {isPublic ? 'Review of public documents' : `Extension of Approval ${a.academic_year}`}
            {' '}{isPublic ? <span className="pill real">Real · public documents</span> : <span className="pill test">Test data</span>}
            {isPublic && <Tip>Only documents this college publishes on its website were checked. Items that need the full application show as “Not public”.</Tip>}</div>
        </div>
        <div style={{ textAlign: 'right' }}><Lane lane={a.lane} /><div className="small faint">{groups.fail.length} problem(s) · {groups.check.length} to check · {groups.pass.length} OK</div></div>
      </div>

      <div className="tabs">
        {[['problems', 'Problems'], ['docs', 'Documents'], ['details', 'Application details'], ['issuer', 'Issuer checks']].map(([k, l]) =>
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}
      </div>

      {tab === 'problems' && <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}>
        <div className="box">
          {groups.fail.length > 0 && <><div className="group-h">Problems found</div>{groups.fail.map((f: any, i: number) => <Item key={f.id} f={f} n={i + 1} />)}</>}
          {groups.check.length > 0 && <><div className="group-h">To check</div>{groups.check.map((f: any, i: number) => <Item key={f.id} f={f} n={groups.fail.length + i + 1} />)}</>}
          {!groups.fail.length && !groups.check.length && <div className="empty">No problems found.</div>}
          <div className="group-h" style={{ cursor: 'pointer' }} onClick={() => setShowPassed(!showPassed)}>
            {showPassed ? '▾' : '▸'} Checks passed ({groups.pass.length}){groups.notes.length ? ` · notes (${groups.notes.length})` : ''}{groups.na.length ? ` · not public (${groups.na.length})` : ''}</div>
          {showPassed && groups.notes.map((f: any, i: number) => <Item key={f.id} f={f} n={groups.fail.length + groups.check.length + i + 1} />)}
          {showPassed && [...groups.pass, ...groups.na].map((f: any) => (
            <div key={f.id} className="issue" style={{ cursor: 'default' }}>
              <span className={`n ${resultColor(f.status)}`}>{f.status === 'pass' ? '✓' : '–'}</span><span>{f.title}</span><Result s={f.status} />
            </div>))}
        </div>
        {staff && <Decision appId={a.id} decision={a.decision} canDecide={user.role === 'scrutiny_officer'} onDone={load} />}
      </div>}

      {tab === 'docs' && <div>
        <div className="row" style={{ marginBottom: 10 }}>
          <span className="small muted">Document:</span>
          <select value={doc?.id} onChange={(e) => { setDocSel(e.target.value); setMarkSel(null) }}>
            {docs.map((x: any) => {
              const n = findings.filter((f: any) => f.status === 'fail' && (f.evidence || []).some((e: any) => e.doc_id === x.id)).length
              return <option key={x.id} value={x.id}>{docTitle(x.declared_type || x.doc_type)} — {x.filename}{n ? `  (${n} problem${n > 1 ? 's' : ''})` : ''}</option>
            })}
          </select>
          {doc?.declared_type && doc.classification?.doc_type && !['unknown', doc.declared_type].includes(doc.classification.doc_type) &&
            <span className="pill orange">Reads like: {docTitle(doc.classification.doc_type)}</span>}
        </div>
        {doc && <DocWithMarks key={doc.id + (markSel || '')} doc={doc} marks={docMarks(doc)} initial={markSel} />}
      </div>}

      {tab === 'details' && <div className="grid">
        <div className="box"><div className="bh"><h3>Courses</h3><span className="small faint">compared with the last approval on record ({d.ledger?.academic_year || '—'})</span></div>
          <table className="t"><thead><tr><th>Course</th><th className="num">Approved</th><th className="num">Applied</th><th /></tr></thead>
            <tbody>{d.delta.length ? d.delta.map((x: any, i: number) => <tr key={i}><td>{titleCase(x.course)}</td><td className="num">{x.approved ?? '—'}</td><td className="num">{x.applied}</td>
              <td>{x.change === 'same' ? '' : <span className={`pill ${x.change === 'increase' || x.change === 'new' ? 'orange' : 'grey'}`}>{x.change}</span>}</td></tr>)
              : d.form.courses.map((c: any, i: number) => <tr key={i}><td>{titleCase(c.course)}</td><td className="num">—</td><td className="num">{c.intake}</td><td /></tr>)}</tbody></table></div>
        {!isPublic && <div className="grid g3">
          <div className="box"><div className="bh"><h3>Faculty</h3><Tip><div className="calc">{d.norms.faculty.derivation.join('\n')}</div></Tip></div>
            <div className="bb"><span style={{ fontSize: 20, fontWeight: 600 }}>{d.form.faculty.length}</span> <span className="muted">on roster · {d.norms.faculty.required} required</span></div></div>
          <div className="box"><div className="bh"><h3>Built-up area</h3><Tip><div className="calc">{d.norms.area.derivation.join('\n')}</div></Tip></div>
            <div className="bb"><span style={{ fontSize: 20, fontWeight: 600 }}>{Math.round(d.form.builtup_area_sqm || 0).toLocaleString('en-IN')}</span> <span className="muted">sq.m · {d.norms.area.required_builtup.toLocaleString('en-IN')} required</span></div></div>
          <div className="box"><div className="bh"><h3>Fee due</h3><Tip><div className="calc">{d.norms.ter.derivation.join('\n')}</div></Tip></div>
            <div className="bb"><span style={{ fontSize: 20, fontWeight: 600 }}>{inr(d.norms.ter.required)}</span></div></div>
        </div>}
        {d.form.faculty.length > 0 && <details className="box"><summary className="bh" style={{ cursor: 'pointer' }}><h3>Faculty list ({d.form.faculty.length})</h3></summary>
          <div style={{ maxHeight: 460, overflow: 'auto' }}><table className="t small"><thead><tr><th>Name</th><th>Faculty ID</th><th>Designation</th><th>Qualification</th><th>Department</th><th>Joined</th></tr></thead>
            <tbody>{d.form.faculty.map((f: any, i: number) => <tr key={i}><td>{f.name}</td><td className="mono">{f.faculty_id}</td><td>{f.designation}</td><td>{f.qualification}</td><td>{titleCase(f.department)}</td><td>{f.date_of_joining}</td></tr>)}</tbody></table></div></details>}
        {isPublic && d.form.public_sources && <div className="box"><div className="bh"><h3>Public sources used</h3></div>
          <table className="t small"><tbody>{Object.entries(d.form.public_sources).map(([k, v]: any) => <tr key={k}><td>{k}</td><td><a href={v} target="_blank" rel="noreferrer">{v}</a></td></tr>)}</tbody></table></div>}
      </div>}

      {tab === 'issuer' && <div className="box">
        <table className="t">
          <thead><tr><th>Document</th><th>Checked with</th><th>Result</th><th>Details</th></tr></thead>
          <tbody>{d.verifications.map((v: any) => {
            const vd = docs.find((x: any) => x.id === v.document_id)
            return <tr key={v.id}>
              <td>{docTitle(vd?.declared_type || vd?.doc_type)}</td>
              <td className="small">{v.source}{v.simulated ? <Tip>Simulated stand-in for the issuer's online service.</Tip> : null}</td>
              <td><Result s={v.status} /></td>
              <td className="small">{v.detail}
                {v.checks?.length > 0 && <details><summary>Field by field</summary><table className="t small"><tbody>{v.checks.map((c: any, i: number) =>
                  <tr key={i}><td>{c.field}</td><td>{String(c.document)}</td><td>{String(c.source)}</td><td>{c.match ? '✓' : '✗'}</td></tr>)}</tbody></table></details>}
                {v.letter && <details><summary>Letter to the issuing office</summary><pre className="calc">{v.letter}</pre></details>}
              </td></tr>
          })}</tbody>
        </table>
        {!d.verifications.length && <div className="empty">No issuer checks.</div>}
      </div>}

      {cite && <ClauseModal citation={cite} onClose={() => setCite(null)} />}
    </div>
  )
}

function Decision({ appId, decision, canDecide, onDone }: { appId: string; decision: any; canDecide: boolean; onDone: () => void }) {
  const [rec, setRec] = useState('recommend_eoa')
  const [note, setNote] = useState('')
  const [err, setErr] = useState<any>(null)
  const submit = async () => {
    setErr(null)
    try { await api(`/api/applications/${appId}/decision`, { method: 'POST', json: { recommendation: rec, note } }); setNote(''); onDone() }
    catch (e: any) { setErr(e instanceof ApiError ? e.body?.detail : { message: e.message }) }
  }
  return (
    <div className="box">
      <div className="bh"><h3>Recommendation</h3>{decision && <span className="small">Last: <b>{decision.decision.replace(/_/g, ' ')}</b> by {decision.actor}, {fmtDate(decision.ts)}</span>}</div>
      <div className="bb">
        {canDecide ? <div className="row">
          <select value={rec} onChange={(e) => setRec(e.target.value)}>
            <option value="recommend_eoa">Recommend approval</option><option value="deficiency_letter">Send deficiency letter</option>
            <option value="refer_verification">Send for document verification</option><option value="refer_evc">Send for site inspection</option>
          </select>
          <input placeholder="Remark (required)" value={note} onChange={(e) => setNote(e.target.value)} style={{ flex: 1, minWidth: 220 }} />
          <button className="btn primary" disabled={note.trim().length < 5} onClick={submit}>Save</button>
          <Tip>A deficiency letter, verification or inspection can only be recorded after every serious problem has been confirmed or dismissed by you.</Tip>
        </div> : <span className="small faint">Only a scrutiny officer can record a recommendation.</span>}
        {err && <div className="note bad" style={{ marginTop: 10 }}>{err.message}{err.unreviewed && <ul className="small" style={{ margin: '6px 0 0' }}>{err.unreviewed.map((u: any) => <li key={u.id}>{u.title}</li>)}</ul>}</div>}
      </div>
    </div>
  )
}
