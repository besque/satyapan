import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getToken } from '../api'
import { docTitle, Result, Tip } from '../ui'

const SLOTS = ['affidavit_2', 'ter_receipt', 'occupancy_certificate', 'structural_stability', 'fire_noc', 'satellite_map', 'audited_statement']

export default function Precheck() {
  const nav = useNavigate()
  const [base, setBase] = useState<any>(null)
  const [files, setFiles] = useState<Record<string, File>>({})
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
      const r = await fetch(`/api/precheck/${base.application.id}/resubmit`, { method: 'POST', body: fd, headers: { 'X-Token': getToken() || '' } })
      const j = await r.json(); if (!r.ok) throw new Error(j.detail || 'failed')
      nav(`/app/${j.application_id}`)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const useFix = async (f: any) => {
    setBusy(true)
    try { const j = await api(`/api/precheck/${base.application.id}/fixes/${f.file}`, { method: 'POST' }); nav(`/app/${j.application_id}`) } finally { setBusy(false) }
  }
  if (!base) return <div className="empty"><span className="spinner" /></div>
  const fails = base.findings.filter((f: any) => f.status === 'fail')
  const docOf = (slot: string) => base.documents.find((d: any) => d.declared_type === slot)
  const issuesFor = (d: any) => d ? fails.filter((f: any) => (f.evidence || []).some((e: any) => e.doc_id === d.id)).length : 0
  return (
    <div>
      <div className="titlebar"><div><h1>Check before submitting <Tip>Replace any document and run the same checks AICTE uses. Nothing is submitted from here.</Tip></h1>
        <div className="sub">{fails.length ? `${fails.length} problem(s) in your last check` : 'No problems in your last check'}</div></div></div>
      <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 360px' }}>
        <div className="box">
          <table className="t">
            <thead><tr><th>Document</th><th>Current file</th><th>Result</th><th>Replace</th></tr></thead>
            <tbody>{SLOTS.map((s) => {
              const d = docOf(s); const n = issuesFor(d)
              return <tr key={s}><td><b>{docTitle(s)}</b></td><td className="small">{d ? d.filename : <span className="faint">Not uploaded</span>}</td>
                <td>{d ? <Result s={n ? 'fail' : 'pass'} /> : <span className="faint">—</span>}</td>
                <td><input type="file" accept="application/pdf" onChange={(e) => { const f = e.target.files?.[0]; if (f) setFiles({ ...files, [s]: f }) }} /></td></tr>
            })}</tbody>
          </table>
          <div className="bb row"><button className="btn primary" disabled={busy || !Object.keys(files).length} onClick={run}>{busy ? 'Checking…' : 'Check again'}</button>
            {err && <span style={{ color: 'var(--red)' }}>{err}</span>}</div>
        </div>
        <div className="grid" style={{ alignContent: 'start' }}>
          <div className="box"><div className="bh"><h3>To fix</h3></div>
            {fails.map((f: any) => <div key={f.id} className="issue" style={{ cursor: 'default' }}><span className="n red">!</span><span className="t1">{f.title}</span><span />
              {f.remedy && <span className="t2">{f.remedy}</span>}</div>)}
            {!fails.length && <div className="empty">Nothing to fix.</div>}</div>
          {fixes.length > 0 && <div className="box"><div className="bh"><h3>Corrected files (demo)</h3></div><div className="bb grid" style={{ gap: 6 }}>
            {fixes.map((f) => <button key={f.file} className="btn" disabled={busy} onClick={() => useFix(f)}>Upload renewed {docTitle(f.declared_type).toLowerCase()}</button>)}</div></div>}
        </div>
      </div>
    </div>
  )
}
