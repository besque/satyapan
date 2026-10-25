import { useEffect, useState } from 'react'
import { api, getToken } from '../api'
import { DocWithMarks, Tip, titleCase, type Mark } from '../ui'

export default function EoaVerifier() {
  const [samples, setSamples] = useState<any[]>([])
  const [sid, setSid] = useState('')
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { api('/api/eoa/samples').then((s) => { setSamples(s); setSid(s[0]?.id || '') }) }, [])
  const run = async (p: Promise<any>) => {
    setBusy(true); setErr(''); setRes(null)
    try { setRes(await p) } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const upload = (f: File) => {
    const fd = new FormData(); fd.append('file', f)
    run(fetch('/api/eoa/verify', { method: 'POST', body: fd, headers: { 'X-Token': getToken() || '' } }).then((r) => r.json()))
  }
  const L = res?.letters?.[0]
  const v = res?.verification
  const marks: Mark[] = []
  if (res) {
    ;(v?.evidence || []).forEach((e: any, i: number) => marks.push({ key: 'v' + i, page: e.page, bbox: e.bbox, color: 'red', title: 'Differs from AICTE record', note: e.label }))
    res.findings.forEach((f: any, i: number) => (f.evidence || []).forEach((e: any, j: number) => marks.push({ key: `f${i}-${j}`, page: e.page, bbox: e.bbox, color: 'red',
      title: f.title, note: e.label, body: <div>{f.detail}</div> })))
  }
  const ok = v?.status === 'verified' && !res?.findings.length
  return (
    <div>
      <div className="titlebar"><div><h1>Check an approval letter <Tip>Compares an AICTE Extension of Approval letter with the approval record and checks the file for edits. The record here is built from {`84+`} real letters that colleges publish on their websites.</Tip></h1>
        <div className="sub">Upload a letter, or try one of the examples</div></div></div>
      <div className="box" style={{ marginBottom: 14 }}>
        <div className="bb row">
          <input type="file" accept="application/pdf" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <span className="faint">or</span>
          <select value={sid} onChange={(e) => setSid(e.target.value)}>
            {samples.map((s) => <option key={s.id} value={s.id}>{s.kind === 'genuine' ? 'Real letter' : s.kind === 'tampered' ? 'Altered copy' : 'Re-saved copy'} — {s.label.replace(/^.*\(/, '').replace(/\)$/, '')}{s.kind === 'tampered' ? ` (${s.label.includes('white-box') ? 'number painted over' : 'number replaced'})` : ''}</option>)}
          </select>
          <button className="btn primary" disabled={!sid || busy} onClick={() => run(api(`/api/eoa/samples/${sid}`, { method: 'POST' }))}>Check</button>
          {busy && <span className="spinner" />}
        </div>
      </div>
      {err && <div className="note bad">{err}</div>}
      {res && <>
        <div className={`note ${ok ? 'ok' : 'bad'}`} style={{ marginBottom: 14, fontSize: 15 }}>
          <b>{ok ? 'Matches the AICTE record' : v?.status === 'mismatch' ? 'Does not match the AICTE record' : res.findings.length ? 'The file has been edited' : 'Could not be confirmed'}</b>
          {L && <> — {titleCase(L.fields.name?.value)}, {L.fields.academic_year?.value} (Permanent ID {L.fields.permanent_id?.value})</>}
          {res.sample?.source_url && <div className="small" style={{ marginTop: 4 }}>Public copy: <a href={res.sample.source_url} target="_blank" rel="noreferrer">{res.sample.source_url}</a></div>}
        </div>
        <div className="grid g2" style={{ marginBottom: 14 }}>
          {v?.checks?.length > 0 && <div className="box"><div className="bh"><h3>Compared with the record</h3></div>
            <table className="t small"><thead><tr><th>Item</th><th>Letter</th><th>Record</th><th /></tr></thead>
              <tbody>{v.checks.map((c: any, i: number) => <tr key={i} style={c.match ? undefined : { background: 'var(--red-bg)' }}><td>{titleCase(c.field)}</td><td>{String(c.document)}</td><td>{String(c.source)}</td><td>{c.match ? '✓' : '✗'}</td></tr>)}</tbody></table></div>}
          <div className="box"><div className="bh"><h3>The file itself</h3></div>
            <table className="t small"><tbody>
              <tr><td>Made by</td><td>{res.forensics?.meta?.producer || '—'} {res.forensics?.meta?.kind === 'reprocessed' && <span className="pill orange">re-saved copy</span>}
                {res.forensics?.meta?.kind === 'reprocessed' && <Tip>Not the portal's original file. Common and not a sign of tampering, but the file cannot prove where it came from, so the record check matters.</Tip>}</td></tr>
              <tr><td>Saved versions</td><td>{res.forensics?.revisions?.revisions?.length}</td></tr>
              <tr><td>Edits found</td><td>{res.findings.length ? <span className="pill red">{res.findings.length}</span> : <span className="pill green">None</span>}</td></tr>
            </tbody></table></div>
        </div>
        <DocWithMarks marks={marks} initial={marks[0]?.key} sizes={res.page_sizes} src={(p) => `/api/eoa/page/${res.sha256}/${p}.png`} />
      </>}
    </div>
  )
}
