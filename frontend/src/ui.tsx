import { useEffect, useRef, useState, type ReactNode } from 'react'
import { img } from './api'

/* ---------- plain words for statuses ---------- */
export const LANE: Record<string, { word: string; color: string; hint: string }> = {
  green: { word: 'Clear', color: 'green', hint: 'No problems found and every certificate was confirmed with its issuer.' },
  amber: { word: 'Needs action', color: 'orange', hint: 'Missing, expired or incomplete items, or a check that a person must finish.' },
  red: { word: 'Alert', color: 'red', hint: 'A document may have been altered, does not match its issuer, or is shared with another institution.' },
}
export function Lane({ lane }: { lane?: string | null }) {
  const l = LANE[lane || ''] || { word: 'Processing', color: 'grey' }
  return <span className={`st ${l.color}`}>{l.word}</span>
}

const RESULT: Record<string, [string, string]> = {
  pass: ['OK', 'green'], fail: ['Problem', 'red'], warn: ['Check', 'orange'], manual: ['Check by hand', 'orange'], na: ['Not public', 'grey'],
  verified: ['Confirmed', 'green'], mismatch: ['Does not match', 'red'], expired: ['Expired', 'orange'], pending: ['Waiting', 'orange'],
  source_unavailable: ['Source offline', 'orange'], manual_review: ['Check by hand', 'orange'],
}
export function Result({ s }: { s: string }) {
  const [w, c] = RESULT[s] || [s, 'grey']
  return <span className={`pill ${c}`}>{w}</span>
}
export const resultColor = (s: string) => (RESULT[s] || ['', 'grey'])[1]

export const docTitle = (t: string) => ({
  affidavit_2: 'Affidavit', ter_receipt: 'Fee receipt', occupancy_certificate: 'Occupancy certificate', structural_stability: 'Structural safety certificate',
  fire_noc: 'Fire safety certificate', satellite_map: 'Location map', audited_statement: 'Audited accounts', infra_photo: 'Photo',
  eoa_letter: 'AICTE approval letter', mandatory_disclosure: 'Public disclosure', unknown: 'Other document',
} as Record<string, string>)[t] || t

/* ---------- small info icon that hides detail ---------- */
export function Tip({ children }: { children: ReactNode }) {
  return <span className="tip" tabIndex={0}><span className="i">i</span><span className="pop">{children}</span></span>
}

/* ---------- document page with ONE highlight at a time ---------- */
export function PageView({ src, size, box, scrollKey }: { src: string; size: number[]; box?: number[] | null; scrollKey?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [w, h] = size
  useEffect(() => {
    if (box && ref.current) ref.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [scrollKey])
  return (
    <div className="pagewrap">
      <img src={src} alt="document page" />
      {box && <div ref={ref} key={scrollKey} className="mark" style={{
        left: `${((box[0] - 3) / w) * 100}%`, top: `${((box[1] - 3) / h) * 100}%`,
        width: `${((box[2] - box[0] + 6) / w) * 100}%`, height: `${((box[3] - box[1] + 6) / h) * 100}%`,
      }} />}
    </div>
  )
}

export type Mark = { key: string; page: number; bbox: number[] | null; title: string; note?: string; color: string; body?: ReactNode }

/** Every marked spot drawn lightly on the page with its number; clicking one (on the page or in the list)
 *  makes it solid and opens its explanation in the side list. */
function MarkedPage({ src, size, marks, sel, onPick }: { src: string; size: number[]; marks: (Mark & { n: number })[]; sel: string | null; onPick: (m: Mark) => void }) {
  const [w, h] = size
  // several findings can point at the same spot: draw one box carrying all their numbers
  const rank: Record<string, number> = { red: 0, violet: 1, orange: 2, green: 3, grey: 4 }
  const groups: (Mark & { n: number })[][] = []
  marks.filter((m) => m.bbox).forEach((m) => {
    const g = groups.find((x) => x[0].bbox!.every((v, i) => Math.abs(v - m.bbox![i]) < 4))
    if (g) g.push(m); else groups.push([m])
  })
  return (
    <div className="pagewrap">
      <img src={src} alt="document page" />
      {groups.map((g) => {
        const b = g[0].bbox!
        const color = [...g].sort((a, c) => (rank[a.color] ?? 9) - (rank[c.color] ?? 9))[0].color
        const on = g.some((m) => m.key === sel)
        return (
          <div key={g[0].key} className={`spot ${color} ${on ? 'on' : ''}`} title={g.map((m) => m.title).join(' · ')} role="button" tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter') onPick(on ? g[(g.findIndex((m) => m.key === sel) + 1) % g.length] : g[0]) }}
            onClick={() => onPick(on ? g[(g.findIndex((m) => m.key === sel) + 1) % g.length] : g[0])}
            style={{ left: `${((b[0] - 3) / w) * 100}%`, top: `${((b[1] - 3) / h) * 100}%`, width: `${((b[2] - b[0] + 6) / w) * 100}%`, height: `${((b[3] - b[1] + 6) / h) * 100}%` }}>
            <span className="tag">{g.map((m) => m.n).join('·')}</span>
          </div>
        )
      })}
    </div>
  )
}

export function DocWithMarks({ doc, marks, initial, src, sizes }: {
  doc?: any; marks: Mark[]; initial?: string | null; src?: (page: number) => string; sizes?: number[][]
}) {
  const [sel, setSel] = useState<string | null>(initial ?? null)
  const [page, setPage] = useState(0)
  const [compare, setCompare] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  useEffect(() => { setSel(initial ?? null); const m = marks.find((x) => x.key === initial); if (m) setPage(m.page) }, [initial, doc?.id])
  useEffect(() => {
    if (sel) listRef.current?.querySelector(`[data-key="${CSS.escape(sel)}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [sel])
  const numbered = marks.map((m, i) => ({ ...m, n: i + 1 }))
  const onPage = numbered.filter((m) => m.page === page)
  const pages = doc?.pages || sizes?.length || 1
  const size = (sizes || doc?.page_sizes)?.[page] || [595, 842]
  const pageSrc = src ? src(page) : img(`/api/documents/${doc.id}/page/${page}.png`)
  const revs = doc?.forensics?.revisions?.revisions || []
  const pick = (m: Mark) => { setSel(m.key === sel ? null : m.key); if (m.page !== page) setPage(m.page) }
  return (
    <div className="split">
      <div>
        <div className="spread" style={{ marginBottom: 6 }}>
          <div className="row">
            {pages > 1 && Array.from({ length: pages }).map((_, i) => (
              <button key={i} className={`btn sm ${i === page ? 'primary' : ''}`} onClick={() => setPage(i)}>Page {i + 1}</button>))}
          </div>
          <div className="row">
            {revs.length > 1 && <button className="btn sm" onClick={() => setCompare(!compare)}>{compare ? 'Hide earlier version' : 'Show earlier version'}</button>}
            {doc && !(doc.mime || '').startsWith('image') && <a className="btn sm" href={img(`/api/documents/${doc.id}/file`)} target="_blank" rel="noreferrer">Open file</a>}
          </div>
        </div>
        {compare && doc ? <div className="grid g2">
          <div><div className="small faint">Earlier version (recovered)</div><MarkedPage src={img(`/api/documents/${doc.id}/revision/0.png?page=${page}`)} size={size} marks={onPage} sel={sel} onPick={pick} /></div>
          <div><div className="small faint">As submitted</div><MarkedPage src={pageSrc} size={size} marks={onPage} sel={sel} onPick={pick} /></div>
        </div> : <MarkedPage src={pageSrc} size={size} marks={onPage} sel={sel} onPick={pick} />}
      </div>
      <div ref={listRef} className="box sticky" style={{ maxHeight: '88vh', overflow: 'auto' }}>
        <div className="bh"><h3>Marked on this document</h3><span className="small faint">click a box on the page</span></div>
        {marks.length === 0 && <div className="empty">Nothing marked.</div>}
        {numbered.map((m) => (
          <div key={m.key} data-key={m.key}>
            <div className={`issue ${sel === m.key ? 'sel' : ''}`} role="button" tabIndex={0} onClick={() => pick(m)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(m) } }}>
              <span className={`n ${m.color}`}>{m.n}</span>
              <span className="t1">{m.title}</span>
              <span className="small faint">{m.bbox ? `p.${m.page + 1}` : ''}</span>
              {m.note && <span className="t2">{m.note}</span>}
            </div>
            {sel === m.key && m.body && <div className="detail">{m.body}</div>}
          </div>
        ))}
      </div>
    </div>
  )
}

export function Modal({ title, children, onClose, full }: { title: ReactNode; children: ReactNode; onClose: () => void; full?: boolean }) {
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className={`modal ${full ? 'full' : ''}`} onClick={(e) => e.stopPropagation()}>
        <div className="bh"><h2>{title}</h2><button className="btn sm" onClick={onClose}>Close</button></div>
        <div style={{ padding: 14, flex: 1, minHeight: 0 }}>{children}</div>
      </div>
    </div>
  )
}

export function ClauseModal({ citation, onClose }: { citation: any; onClose: () => void }) {
  const loc = citation?.loc
  return (
    <Modal title={`Approval Process Handbook · ${citation.ref}`} onClose={onClose}>
      {loc ? <div style={{ position: 'relative' }}>
        <div className="pagewrap"><img src={`/api/aph/page/${loc.pdf_page}.png`} alt="handbook page" />
          {loc.rects.map((r: number[], i: number) => <div key={i} className="mark" style={{
            left: `${((r[0] - 2) / loc.page_size[0]) * 100}%`, top: `${((r[1] - 2) / loc.page_size[1]) * 100}%`,
            width: `${((r[2] - r[0] + 4) / loc.page_size[0]) * 100}%`, height: `${((r[3] - r[1] + 4) / loc.page_size[1]) * 100}%` }} />)}
        </div>
      </div> : <div className="quote">{citation.quote}</div>}
    </Modal>
  )
}

export const fmtDate = (s?: string | null) => s ? new Date(s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
export const inr = (n: number) => '₹' + Math.round(n).toLocaleString('en-IN')
export const titleCase = (s?: string | null) => (s || '').toLowerCase().replace(/\b([a-z])/g, (m) => m.toUpperCase()).replace(/\bOf\b/g, 'of').replace(/\bAnd\b/g, 'and')
