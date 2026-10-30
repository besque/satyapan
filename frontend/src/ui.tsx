import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { api } from './api'

/* ---------- dates ---------- */
const D = (s: string) => new Date(s.length <= 10 ? s + 'T00:00:00' : s)
export const fmtDate = (s?: string | null) => s ? D(s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
export const fmtShort = (s?: string | null) => s ? D(s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) : '—'
export const fmtLong = (s?: string | null) => s ? D(s).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) : ''
export const fmtTime = (s?: string | null) => s ? D(s).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
export const days = (a: string, b: string) => Math.round((D(b).getTime() - D(a).getTime()) / 86400000)
export const titleCase = (s?: string | null) => (s || '').toLowerCase().replace(/\b([a-z])/g, (m) => m.toUpperCase()).replace(/\b(Of|And|For|In)\b/g, (m) => m.toLowerCase())
export const nameOf = (s?: string | null) => s && s === s.toUpperCase() ? titleCase(s) : (s || '')

/* ---------- the countdown in plain words ---------- */
export const RISK: Record<string, { word: string; color: string; hint: string }> = {
  on_track: { word: 'On track', color: 'green', hint: 'Will be decided before the Academic Calendar date even if one more round of deficiencies comes up.' },
  at_risk: { word: 'At risk', color: 'orange', hint: 'Makes the date at the usual pace, but one more round of deficiencies would push the decision past it.' },
  fast_track: { word: 'Needs fast-tracking', color: 'red', hint: 'At the usual pace the decision comes after the date. Holding the remaining committees at the minimum notice still makes it.' },
  will_miss: { word: 'Will miss the date', color: 'darkred', hint: 'Even at the fastest possible pace the decision would come after the date. Decide early what to tell the institution.' },
}
export function Risk({ r, spare, plain }: { r?: string | null; spare?: number | null; plain?: boolean }) {
  if (!r) return <span className="faint">—</span>
  const x = RISK[r]
  return <span className="row" style={{ gap: 6 }}><span className={`st ${x.color}`}>{x.word}</span>
    {!plain && spare !== undefined && spare !== null && <span className="spare">{spare >= 0 ? `${spare} d spare` : `${-spare} d short`}</span>}</span>
}

export function Due({ due, overdue, left }: { due?: string | null; overdue?: number; left?: number | null }) {
  if (!due) return <span className="faint">—</span>
  if (overdue && overdue > 0) return <span className="due red">Overdue {overdue} d</span>
  if (left !== undefined && left !== null && left <= 3) return <span className="due orange">{left === 0 ? 'Due today' : `Due in ${left} d`}</span>
  return <span className="due grey">Due {fmtShort(due)}</span>
}

export function Holder({ kind, label, days: n }: { kind?: string | null; label?: string | null; days?: number | null }) {
  if (!kind) return <span className="faint">—</span>
  return <span className={`holder ${kind}`} title={kind === 'institution' ? 'The ball is with the institution' : 'The ball is with AICTE'}>
    <i />{label}{n !== undefined && n !== null && <span className="faint"> · {n} d</span>}</span>
}

export const Source = ({ s }: { s?: string | null }) => s === 'public'
  ? <span className="pill real" title="From AICTE letters and documents the institution has published">Public record</span> : null

/* ---------- small info icon that hides detail ---------- */
export function Tip({ children }: { children: ReactNode }) {
  // The pop-up is rendered on <body> with fixed positioning, so no box, table or strip can clip it.
  const ref = useRef<HTMLSpanElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number; up: boolean } | null>(null)
  const show = () => {
    const r = ref.current?.getBoundingClientRect()
    if (!r) return
    const w = Math.min(300, window.innerWidth - 24)
    const left = Math.max(12, Math.min(r.left - 10, window.innerWidth - w - 12))
    const up = r.bottom + 160 > window.innerHeight && r.top > 180
    setPos({ left, top: up ? r.top - 6 : r.bottom + 6, up })
  }
  return (
    <span ref={ref} className="tip" tabIndex={0} onMouseEnter={show} onMouseLeave={() => setPos(null)} onFocus={show} onBlur={() => setPos(null)}
      onClick={(e) => { e.stopPropagation(); pos ? setPos(null) : show() }}>
      <span className="i">i</span>
      {pos && createPortal(
        <span className="pop-float" style={{ left: pos.left, top: pos.top, transform: pos.up ? 'translateY(-100%)' : undefined }}>{children}</span>,
        document.body)}
    </span>
  )
}

export function Modal({ title, children, onClose, wide, actions }: { title: ReactNode; children: ReactNode; onClose: () => void; wide?: boolean; actions?: ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className={`modal ${wide ? 'wide' : ''}`} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="bh"><h2>{title}</h2><div className="row">{actions}<button className="btn sm" onClick={onClose}>Close</button></div></div>
        <div style={{ padding: 14 }}>{children}</div>
      </div>
    </div>
  )
}

/* ---------- handbook clause: opens the page with the quoted text highlighted ---------- */
export function Cite({ c, label }: { c?: any; label?: string }) {
  const [open, setOpen] = useState(false)
  if (!c) return null
  return <>
    <button className="cite" onClick={(e) => { e.stopPropagation(); setOpen(true) }} title="Open the handbook page">{label || (c.source === 'letter' ? 'EoA letter' : c.ref)}</button>
    {open && <ClauseModal c={c} onClose={() => setOpen(false)} />}
  </>
}

export function ClauseModal({ c, onClose }: { c: any; onClose: () => void }) {
  const [full, setFull] = useState<any>(c.loc || c.source === 'letter' ? c : null)
  useEffect(() => { if (!full) api(`/api/aph/${c.key}`).then(setFull).catch(() => setFull(c)) }, [])
  const loc = full?.loc
  return (
    <Modal wide title={c.source === 'letter' ? c.ref : `Approval Process Handbook 2024-27 · ${c.ref}`} onClose={onClose}>
      {!full ? <div className="empty"><span className="spinner" /></div> : loc ? <>
        <div className="small faint" style={{ marginBottom: 6 }}>Page {loc.printed_page ?? loc.pdf_page + 1} of the handbook. The quoted text is highlighted.</div>
        <div className="pagewrap"><img src={`/api/aph/page/${loc.pdf_page}.png`} alt="handbook page" />
          {loc.rects.map((r: number[], i: number) => <div key={i} className="mark" style={{
            left: `${((r[0] - 2) / loc.page_size[0]) * 100}%`, top: `${((r[1] - 2) / loc.page_size[1]) * 100}%`,
            width: `${((r[2] - r[0] + 4) / loc.page_size[0]) * 100}%`, height: `${((r[3] - r[1] + 4) / loc.page_size[1]) * 100}%` }} />)}
        </div></> : <div className="stack"><div className="quote">{full.quote}</div>{full.note && <div className="small muted">{full.note}</div>}</div>}
    </Modal>
  )
}

/* ---------- the stages of the application (APH Table 2.3) ---------- */
export function RouteStrip({ chips }: { chips: any[] }) {
  return (
    <div className="route">
      {chips.map((c, i) => (
        <div key={i} className={`rchip ${c.state} ${c.outcome || ''}`} title={c.state === 'maybe' ? 'Only if the previous step finds deficiencies (as applicable)' : ''}>
          <b>{c.label}{c.attempt > 1 ? ` (${c.attempt})` : ''}</b>
          <small>{c.state === 'done' ? `${c.outcome_label || 'Done'} · ${fmtShort(c.closed_on)}` : c.state === 'current' ? `Now: ${c.holder_label || ''}` : c.state === 'next' ? 'Next' : 'If needed'}</small>
        </div>))}
    </div>
  )
}

/* ---------- the remaining path drawn against the calendar date ---------- */
export function PathBar({ cd, today }: { cd: any; today: string }) {
  const segs = cd.segments || []
  if (!segs.length) return null
  const t0 = D(today).getTime()
  const end = Math.max(D(cd.deadline).getTime(), D(segs[segs.length - 1].to).getTime()) + 2 * 86400000
  const span = Math.max(end - t0, 86400000)
  const pos = (s: string) => Math.max(0, Math.min(100, ((D(s).getTime() - t0) / span) * 100))
  const dl = D(cd.deadline).getTime()
  return (
    <div className="pathbar">
      <div className="track">
        {segs.map((s: any, i: number) => <div key={i} className={`pseg ${s.current ? 'cur' : ''} ${D(s.to).getTime() > dl ? 'late' : ''}`}
          style={{ left: `${pos(s.from)}%`, width: `${Math.max(1.2, pos(s.to) - pos(s.from))}%` }} title={`${s.label}: ${fmtShort(s.from)} to ${fmtShort(s.to)}`}>{s.label}</div>)}
        <div className="dl" style={{ left: `${pos(cd.deadline)}%` }}><span>{fmtShort(cd.deadline)}</span></div>
      </div>
      <div className="axis"><span>Today, {fmtShort(today)}</span><span>Decision at the usual pace: {fmtShort(cd.decided_by)}</span></div>
    </div>
  )
}

export function SplitBar({ aicte, institution }: { aicte: number; institution: number }) {
  const t = Math.max(1, aicte + institution)
  return <div>
    <div className="splitbar"><i className="aicte" style={{ width: `${(aicte / t) * 100}%` }} /><i className="inst" style={{ width: `${(institution / t) * 100}%` }} /></div>
    <div className="legend" style={{ marginTop: 5 }}><span><i className="sw aicte" />With AICTE {aicte} d</span><span><i className="sw inst" />With the institution {institution} d</span></div>
  </div>
}

export function Counts({ items, on, set }: { items: { k: string; v: ReactNode; l: ReactNode; color?: string }[]; on?: string; set?: (k: string) => void }) {
  return <div className="counts">{items.map((x) => set
    ? <button key={x.k} className={on === x.k ? 'on' : ''} onClick={() => set(x.k)}><span className="v" style={{ color: x.color ? `var(--${x.color})` : undefined }}>{x.v}</span><span className="l">{x.l}</span></button>
    : <div key={x.k}><span className="v" style={{ color: x.color ? `var(--${x.color})` : undefined }}>{x.v}</span><span className="l">{x.l}</span></div>)}</div>
}

export const AppLink = ({ id }: { id: string }) => <Link className="mono" to={`/app/${id}`}>{id}</Link>
export const InstLink = ({ pid, name }: { pid?: string | null; name?: string | null }) => pid ? <Link to={`/institution/${pid}`}>{nameOf(name) || pid}</Link> : null
export const Loading = () => <div className="empty"><span className="spinner" /></div>
