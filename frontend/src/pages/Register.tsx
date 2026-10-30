import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useUser } from '../App'
import { B, CaseLink, Marked, Status, Tip } from '../ui'

const EXAMPLES = [
  { label: 'Hindi complaint, already filed elsewhere', inst_text: 'नीलकमल तराई इंजीनियरिंग कॉलेज लखनऊ', subject: 'मार्कशीट और टीसी नहीं लौटाई',
    description: 'कॉलेज छोड़ने के बाद नीलकमल तराई इंजीनियरिंग कॉलेज मेरी 10वीं, 12वीं की अंकतालिका और टीसी नहीं लौटा रहा है और 45,000 रुपये मांग रहा है।', complainant: 'Pooja Yadav', contact: '' },
  { label: 'Acronym and misspelling', inst_text: 'KIT Indore (Kesarvani)', subject: 'Refund not given',
    description: 'I withdrew from B.Tech at Kesarvani institute Indore in August. They have not returned Rs 60,000 and keep asking me to visit again.', complainant: 'Rahul Mehta', contact: '' },
  { label: 'Ragging sent to the wrong cell', inst_text: 'Tejasvarna engg clg Hyderabad', subject: 'Seniors beating juniors',
    description: 'In Tejasvarna college hostel seniors beat my cousin and made him stand all night. Nobody from the college helped.', complainant: 'Kiran Rao', contact: '' },
]

export default function Register() {
  const [tab, setTab] = useState<'one' | 'import'>('one')
  return (
    <div>
      <div className="titlebar"><div><h1>Register a complaint</h1><div className="sub">The institution, nature and any duplicate are worked out as you type</div></div></div>
      <div className="tabs">
        <button className={tab === 'one' ? 'on' : ''} onClick={() => setTab('one')}>One complaint</button>
        <button className={tab === 'import' ? 'on' : ''} onClick={() => setTab('import')}>Import a register (CSV)</button>
      </div>
      {tab === 'one' ? <One /> : <Import />}
    </div>
  )
}

function One() {
  const u = useUser()
  const nav = useNavigate()
  const [meta, setMeta] = useState<any>(null)
  const [f, setF] = useState<any>({ bureau: u.bureau || 'PGRC', source: u.bureau === 'PGRC' ? 'CPGRAMS' : 'Letter', ext_ref: '', received_on: new Date().toLocaleDateString('en-CA'),
    complainant: '', complainant_type: 'Student', contact: '', inst_text: '', subject: '', description: '', category: '', permanent_id: '' })
  const [a, setA] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const t = useRef<number>()
  useEffect(() => { api('/api/meta').then(setMeta) }, [])
  useEffect(() => {
    window.clearTimeout(t.current)
    if (!f.inst_text.trim() && !f.description.trim()) { setA(null); return }
    t.current = window.setTimeout(() => api('/api/analyse', { method: 'POST', json: { inst_text: f.inst_text, subject: f.subject, description: f.description, bureau: f.bureau, complainant: f.complainant } }).then(setA).catch(() => {}), 450)
  }, [f.inst_text, f.subject, f.description, f.bureau, f.complainant])
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value })
  const save = async () => {
    setErr(''); setBusy(true)
    try {
      const body = { ...f, category: f.category || null, permanent_id: f.permanent_id || null }
      const r = await api('/api/cases', { method: 'POST', json: body })
      nav(`/case/${r.id}`)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const m = a?.match
  return (
    <div className="split">
      <div className="box">
        <div className="bh"><h2>Complaint</h2>
          <span className="row small">Try: {EXAMPLES.map((x) => <button key={x.label} className="btn sm" onClick={() => setF({ ...f, ...x, label: undefined })}>{x.label}</button>)}</span></div>
        <div className="bb form">
          <label>Bureau / Cell<select value={f.bureau} onChange={set('bureau')} disabled={u.role === 'officer'}>
            {meta?.bureaus.map((b: any) => <option key={b.id} value={b.id}>{b.id} · {b.name}</option>)}</select></label>
          <label>Received through<select value={f.source} onChange={set('source')}>
            {['CPGRAMS', 'Letter', 'E-mail', 'MoE reference', 'State Government reference', 'Anti-Ragging Helpline', 'Court', 'Suo motu'].map((s) => <option key={s}>{s}</option>)}</select></label>
          <label>Reference no.<input value={f.ext_ref} onChange={set('ext_ref')} placeholder="CPGRAMS / letter no." /></label>
          <label>Received on<input type="date" value={f.received_on} onChange={set('received_on')} /></label>
          <label>Complainant<input value={f.complainant} onChange={set('complainant')} /></label>
          <label>Complainant is<select value={f.complainant_type} onChange={set('complainant_type')}>{['Student', 'Parent', 'Faculty', 'Staff', 'Other'].map((s) => <option key={s}>{s}</option>)}</select></label>
          <label><span>Phone / e-mail <Tip>Stored only as a fingerprint, used to spot the same person filing again. The number itself is not kept.</Tip></span><input value={f.contact} onChange={set('contact')} /></label>
          <label className="full">Institution, as written by the complainant<input value={f.inst_text} onChange={set('inst_text')} placeholder="e.g. KIT Indore, नीलकमल तराई कॉलेज, Ratnaparvat Business School" /></label>
          <label className="full">Subject<input value={f.subject} onChange={set('subject')} /></label>
          <label className="full">Complaint (any language)<textarea style={{ minHeight: 120 }} value={f.description} onChange={set('description')} /></label>
          <div className="full row" style={{ justifyContent: 'flex-end' }}>
            {err && <span className="note bad">{err}</span>}
            <button className="btn primary" disabled={busy || !f.inst_text.trim() || !f.description.trim()} onClick={save}>Register complaint</button>
          </div>
        </div>
      </div>
      <div className="grid sticky" style={{ gap: 14 }}>
        <div className="box">
          <div className="bh"><h2>Institution</h2>{m && <span className={`pill ${m.state === 'auto' ? 'green' : m.state === 'confirm' ? 'orange' : 'red'}`}>{m.state === 'auto' ? 'Identified' : m.state === 'confirm' ? 'Choose one' : 'Not found'}</span>}</div>
          <div className="bb">
            {!m && <div className="faint small">Type the institution name as the complainant wrote it.</div>}
            {m && a.inst_spans?.length > 0 && <div className="small" style={{ marginBottom: 6 }}><Marked text={f.inst_text} spans={a.inst_spans} /></div>}
            {m?.candidates.filter((_: any, i: number) => m.state !== 'auto' || i === 0).map((c: any, i: number) => (
              <label key={c.permanent_id} className={`cand ${i === 0 && m.state === 'auto' ? 'best' : ''}`}>
                <div><b>{c.name}</b> <span className="small faint">{c.city} · {Math.round(c.confidence * 100)}%</span>
                  <ul className="why">{c.reasons.map((r: string, j: number) => <li key={j}>{r}</li>)}</ul></div>
                {m.state !== 'auto' && <input type="radio" name="pid" checked={f.permanent_id === c.permanent_id} onChange={() => setF({ ...f, permanent_id: c.permanent_id })} />}
              </label>))}
          </div>
        </div>
        <div className="box">
          <div className="bh"><h2>Nature</h2>{a && <span className="small faint">{a.lang === 'hi' ? 'Hindi' : 'English'}</span>}</div>
          <div className="bb">
            {!a && <div className="faint small">Write the complaint to see its nature.</div>}
            {a?.categories.map((c: any, i: number) => (
              <label key={c.category} className="catopt"><input type="radio" name="cat" checked={(f.category || a.categories[0].category) === c.category} onChange={() => setF({ ...f, category: c.category })} />
                <span>{c.label}</span><span className="track"><i style={{ width: `${Math.max(0, c.score) * 100}%`, opacity: i ? 0.5 : 1 }} /></span></label>))}
            {a?.wrong_bureau && <div className="note" style={{ marginTop: 8 }}>Usually handled by <B b={a.suggested_bureau} />. It can be registered here and transferred.</div>}
          </div>
        </div>
        <div className={`box ${a?.possible_duplicates?.length ? 'attn' : ''}`}>
          <div className="bh"><h2>Already filed?</h2></div>
          <div className="bb">
            {!a?.possible_duplicates?.length && <div className="faint small">{a ? 'No similar complaint on this institution.' : 'Checked once the institution is known.'}</div>}
            {a?.possible_duplicates?.map((x: any) => <div key={x.case} className="rel same">
              <div className="spread"><span><CaseLink id={x.case} /> <B b={x.bureau} /> <Status s={x.status} /></span><span className="pill orange">{Math.round(x.score * 100)}%</span></div>
              <div className="small">{x.subject}</div>
              <ul className="why">{x.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
            </div>)}
          </div>
        </div>
      </div>
    </div>
  )
}

const SAMPLE = `Reference,Received,Complainant,Contact,Institution,Subject,Complaint
L/118/2026,2026-10-12,Meera Iyer,meera.i@example.in,Vaigaivani Inst of Tech Madurai,Certificates not returned,The college is keeping my original certificates and asks for Rs 40000 to return them.
L/119/2026,2026-10-14,Harpreet Gill,9814022211,SIT Ludhiana (Sutlejdhara),Refund pending,I cancelled admission in July; refund of Rs 55000 not given yet.
L/120/2026,2026-10-15,Ramesh Kumar,9839011122,गंगोत्री विहार प्रौद्योगिकी संस्थान कानपुर,वेतन नहीं मिला,संस्थान में शिक्षकों को चार महीने से वेतन नहीं मिला है।`

function Import() {
  const nav = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [r, setR] = useState<any>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const run = async (commit: number) => {
    if (!file) return
    setErr(''); setBusy(true)
    const fd = new FormData(); fd.append('file', file)
    try { setR(await api(`/api/import?commit=${commit}`, { method: 'POST', body: fd })) } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const sample = () => {
    const url = URL.createObjectURL(new Blob([SAMPLE], { type: 'text/csv' }))
    const a = document.createElement('a'); a.href = url; a.download = 'sample_register.csv'; a.click(); URL.revokeObjectURL(url)
  }
  return (
    <div className="box">
      <div className="bh"><h2>Import a bureau register</h2><button className="btn sm" onClick={sample}>Download a sample file</button></div>
      <div className="bb">
        <p className="muted" style={{ marginTop: 0 }}>Bureaus that keep a register in a spreadsheet can save it as CSV and load it here. Columns are recognised by name (reference, date, complainant, contact, institution, subject, complaint). Every row is matched to an institution and checked against cases already on record before anything is saved.</p>
        <div className="row">
          <input type="file" accept=".csv,text/csv" onChange={(e) => { setFile(e.target.files?.[0] || null); setR(null) }} />
          <button className="btn" disabled={!file || busy} onClick={() => run(0)}>Check rows</button>
          {r && !r.committed && <button className="btn primary" disabled={busy} onClick={() => run(1)}>Import {r.rows.length} rows</button>}
          {busy && <span className="spinner" />}
        </div>
        {err && <div className="note bad" style={{ marginTop: 8 }}>{err}</div>}
        {r && <div className="tablewrap" style={{ marginTop: 12 }}><table className="t small">
          <thead><tr><th>Ref.</th><th>Written as</th><th>Institution found</th><th>Nature</th><th>Usually with</th><th>Similar case on record</th>{r.committed && <th>Saved as</th>}</tr></thead>
          <tbody>{r.rows.map((x: any, i: number) => <tr key={i}>
            <td>{x.ref}</td><td>{x.inst_text}</td>
            <td>{x.institution} <span className={`pill ${x.match === 'auto' ? 'green' : 'orange'}`}>{x.match === 'auto' ? `${Math.round(x.confidence * 100)}%` : 'confirm'}</span></td>
            <td>{x.category}</td><td><B b={x.suggested_bureau} /></td>
            <td>{x.duplicates.length ? x.duplicates.map((c: string) => <div key={c}><Link to={`/case/${c}`} className="mono">{c}</Link></div>) : <span className="faint">—</span>}</td>
            {r.committed && <td>{x.id && <a className="mono" href={`/case/${x.id}`} onClick={(e) => { e.preventDefault(); nav(`/case/${x.id}`) }}>{x.id}</a>}</td>}
          </tr>)}</tbody>
        </table></div>}
      </div>
    </div>
  )
}
