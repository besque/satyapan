import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getToken } from '../api'
import { docTitle, Result, Tip } from '../ui'

const SLOTS = ['affidavit_2', 'ter_receipt', 'occupancy_certificate', 'structural_stability', 'fire_noc', 'satellite_map', 'audited_statement']
const FAC_COLS = ['name', 'faculty_id', 'designation', 'qualification', 'department', 'date_of_joining', 'dob', 'pan', 'gender']
const FAC_RULES = ['NORM-FSR', 'NORM-CADRE']

/** Small CSV reader (handles quoted fields) so a list saved from Excel can be uploaded. */
function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = []
  let row: string[] = [], cell = '', q = false
  const t = text.replace(/^﻿/, '')
  for (let i = 0; i < t.length; i++) {
    const c = t[i]
    if (q) {
      if (c === '"' && t[i + 1] === '"') { cell += '"'; i++ } else if (c === '"') q = false; else cell += c
    } else if (c === '"') q = true
    else if (c === ',') { row.push(cell); cell = '' }
    else if (c === '\n' || c === '\r') { if (c === '\r' && t[i + 1] === '\n') i++; row.push(cell); rows.push(row); row = []; cell = '' }
    else cell += c
  }
  if (cell || row.length) { row.push(cell); rows.push(row) }
  const head = (rows.shift() || []).map((h) => h.trim().toLowerCase().replace(/\s+/g, '_'))
  return rows.filter((r) => r.some((x) => x.trim())).map((r) => Object.fromEntries(head.map((h, i) => [h, (r[i] || '').trim()])))
}

function downloadCsv(faculty: any[], name: string) {
  const esc = (v: any) => { const s = String(v ?? ''); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s }
  const csv = [FAC_COLS.join(','), ...faculty.map((f) => FAC_COLS.map((c) => esc(f[c])).join(','))].join('\n')
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv' }))
  a.download = name; a.click(); URL.revokeObjectURL(a.href)
}

export default function Precheck() {
  const nav = useNavigate()
  const [base, setBase] = useState<any>(null)
  const [files, setFiles] = useState<Record<string, File>>({})
  const [faculty, setFaculty] = useState<{ name: string; rows: Record<string, string>[] } | null>(null)
  const [fixes, setFixes] = useState<any[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => {
    api('/api/applications').then(async (x) => {
      const latest = [...x].sort((a: any, b: any) => (b.processed_at || '').localeCompare(a.processed_at || ''))[0]
      if (!latest) return
      setBase(await api(`/api/applications/${latest.id}`))
      setFixes(await api(`/api/precheck/${latest.id}/fixes`))
    })
  }, [])
  const run = async () => {
    setBusy(true); setErr('')
    try {
      const fd = new FormData(); const declared: Record<string, string> = {}
      Object.entries(files).forEach(([slot, f]) => { fd.append('files', f, f.name); declared[f.name] = slot })
      fd.append('declared', JSON.stringify(declared))
      if (faculty) fd.append('form', JSON.stringify({ faculty: faculty.rows }))
      const r = await fetch(`/api/precheck/${base.application.id}/resubmit`, { method: 'POST', body: fd, headers: { 'X-Token': getToken() || '' } })
      const j = await r.json(); if (!r.ok) throw new Error(j.detail || 'failed')
      nav(`/app/${j.application_id}`)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const useFix = async (f: any) => {
    setBusy(true)
    try { const j = await api(`/api/precheck/${base.application.id}/fixes/${f.file}`, { method: 'POST' }); nav(`/app/${j.application_id}`) } finally { setBusy(false) }
  }
  const readFaculty = async (f: File) => {
    const rows = parseCsv(await f.text())
    if (!rows.length || !('name' in rows[0])) { setErr('The faculty file needs a header row with at least a "name" column.'); return }
    setErr(''); setFaculty({ name: f.name, rows })
  }
  if (!base) return <div className="empty"><span className="spinner" /></div>
  const fails = base.findings.filter((f: any) => f.status === 'fail')
  const facFails = fails.filter((f: any) => FAC_RULES.includes(f.rule_id))
  const required = base.norms?.faculty?.required
  const docOf = (slot: string) => base.documents.find((d: any) => d.declared_type === slot)
  const slotOf = (f: any) => {
    if (FAC_RULES.includes(f.rule_id)) return 'faculty'
    const d = base.documents.find((x: any) => x.id === f.document_id || (f.evidence || []).some((e: any) => e.doc_id === x.id))
    if (d && SLOTS.includes(d.declared_type)) return d.declared_type
    const m: Record<string, string> = { 'DOC-AFFIDAVIT': 'affidavit_2', 'DOC-TER': 'ter_receipt', 'DOC-OC': 'occupancy_certificate', 'DOC-SSC': 'structural_stability',
      'DOC-FIRE': 'fire_noc', 'DOC-MAP': 'satellite_map', 'DOC-AUDIT': 'audited_statement' }
    return m[f.rule_id]
  }
  const goSlot = (slot: string) => {
    const row = document.getElementById(`slot-${slot}`)
    if (!row) return
    row.scrollIntoView({ behavior: 'smooth', block: 'center' })
    row.classList.remove('slot-flash'); void row.offsetWidth; row.classList.add('slot-flash')
    ;(row.querySelector('input[type=file]') as HTMLInputElement | null)?.focus()
  }
  const issuesFor = (d: any) => d ? fails.filter((f: any) => f.document_id === d.id || (f.evidence || []).some((e: any) => e.doc_id === d.id)).length : 0
  const changes = Object.keys(files).length + (faculty ? 1 : 0)
  return (
    <div>
      <div className="titlebar"><div><h1>Check before submitting <Tip>Replace any document or update your faculty list, then run the same checks AICTE uses. Nothing is submitted from here.</Tip></h1>
        <div className="sub">{fails.length ? `${fails.length} problem(s) in your last check` : 'No problems in your last check'}</div></div></div>
      <div className="grid split-pre" style={{ gridTemplateColumns: 'minmax(0,1fr) 360px' }}>
        <div className="box">
          <div className="tablewrap"><table className="t">
            <thead><tr><th>Item</th><th>Current</th><th>Result</th><th>Replace</th></tr></thead>
            <tbody>
              {SLOTS.map((s) => {
                const d = docOf(s); const n = issuesFor(d)
                return <tr key={s} id={`slot-${s}`}><td><b>{docTitle(s)}</b></td><td className="small">{files[s] ? <b>{files[s].name}</b> : d ? d.filename : <span className="faint">Not uploaded</span>}</td>
                  <td>{d ? <Result s={n ? 'fail' : 'pass'} /> : <span className="faint">—</span>}</td>
                  <td><input type="file" accept="application/pdf" onChange={(e) => { const f = e.target.files?.[0]; if (f) setFiles({ ...files, [s]: f }) }} /></td></tr>
              })}
              <tr id="slot-faculty">
                <td><b>Faculty list</b></td>
                <td className="small">{faculty ? <><b>{faculty.name}</b><div>{faculty.rows.length} faculty in new list</div></>
                  : <>{base.form.faculty.length} faculty · {required} required</>}
                  <div><button className="btn sm" style={{ marginTop: 4 }} onClick={() => downloadCsv(base.form.faculty, 'faculty_list.csv')}>Download current list (CSV)</button></div></td>
                <td><Result s={facFails.length ? 'fail' : 'pass'} /></td>
                <td><input type="file" accept=".csv,text/csv" onChange={(e) => { const f = e.target.files?.[0]; if (f) readFaculty(f) }} />
                  <div className="small faint" style={{ marginTop: 4 }}>Edit the downloaded list in Excel, save as CSV, upload</div></td>
              </tr>
            </tbody>
          </table></div>
          <div className="bb row"><button className="btn primary" disabled={busy || !changes} onClick={run}>{busy ? 'Checking…' : 'Check again'}</button>
            {changes > 0 && <span className="small muted">{changes} change(s) ready</span>}
            {err && <span style={{ color: 'var(--red)' }}>{err}</span>}</div>
        </div>
        <div className="grid" style={{ alignContent: 'start' }}>
          <div className="box"><div className="bh"><h3>To fix</h3></div>
            {fails.map((f: any) => {
              const slot = slotOf(f)
              return <div key={f.id} className="issue" style={{ cursor: 'default' }}><span className="n red">!</span><span className="t1">{f.title}</span>
                {slot ? <button className="btn sm" onClick={() => goSlot(slot)}>{slot === 'faculty' ? 'Update faculty list' : 'Replace file'}</button> : <span />}
                {f.remedy && <div className="fix"><b>How to fix:</b><span>{f.remedy}</span></div>}</div>
            })}
            {!fails.length && <div className="empty">Nothing to fix.</div>}</div>
          {fixes.length > 0 && <div className="box"><div className="bh"><h3>Corrected files (demo)</h3></div><div className="bb grid" style={{ gap: 6 }}>
            {fixes.map((f) => <button key={f.file} className="btn" disabled={busy} onClick={() => useFix(f)}>
              {f.declared_type === 'faculty' ? 'Upload updated faculty list' : `Upload renewed ${docTitle(f.declared_type).toLowerCase()}`}</button>)}</div></div>}
        </div>
      </div>
    </div>
  )
}
