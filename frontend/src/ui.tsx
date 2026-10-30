import { useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'

/* ---------- plain words for statuses ---------- */
export const STATUS: Record<string, { word: string; color: string }> = {
  pending: { word: 'Pending', color: 'orange' },
  under_process: { word: 'Under process', color: 'blue' },
  transferred: { word: 'Transferred', color: 'violet' },
  disposed: { word: 'Disposed', color: 'green' },
}
export function Status({ s, esc }: { s: string; esc?: number }) {
  if (s !== 'disposed' && (esc ?? -1) >= 2) return <span className="st red">Escalated</span>
  const l = STATUS[s] || { word: s, color: 'grey' }
  return <span className={`st ${l.color}`}>{l.word}</span>
}

export const KIND: Record<string, { word: string; color: string; hint: string }> = {
  conflict: { word: 'Conflicting actions', color: 'red', hint: 'Two bureaus have taken actions that clash, for example approval moving ahead while a show-cause is pending.' },
  duplicate: { word: 'Same matter in two places', color: 'orange', hint: 'The same complaint is open in two files. One bureau should lead; the others link to it.' },
  pattern: { word: 'Many complaints, one issue', color: 'violet', hint: 'Several different people report the same issue at one institution. One inquiry settles all of them.' },
  parallel: { word: 'Parallel cases', color: 'grey', hint: 'More than one bureau has an open case on this institution. They should know of each other.' },
}
const SHORT: Record<string, string> = { conflict: 'Conflict', duplicate: 'Duplicate', pattern: 'Pattern', parallel: 'Parallel' }
export function Kind({ k, short }: { k: string; short?: boolean }) {
  const x = KIND[k] || { word: k, color: 'grey' }
  return <span className={`pill ${x.color}`}>{short ? SHORT[k] || x.word : x.word}</span>
}

export function Due({ t }: { t: any }) {
  if (!t) return null
  const c = t.state === 'overdue' ? 'red' : t.state === 'due_soon' ? 'orange' : t.state === 'late' ? 'orange' : t.state === 'in_time' ? 'green' : 'grey'
  return <span className={`due ${c}`} title={t.escalation || ''}>{t.label}</span>
}

/** How far through its timeline a case is: a thin bar. */
export function Meter({ t }: { t: any }) {
  if (!t) return null
  const pct = Math.min(100, Math.round((t.share || 0) * 100))
  const c = t.state === 'overdue' ? 'red' : t.state === 'due_soon' ? 'orange' : t.state === 'late' ? 'orange' : 'green'
  return <span className="meter" title={`${t.age} of ${t.total} days`}><i className={c} style={{ width: `${pct}%` }} /></span>
}

export const B = ({ b }: { b?: string | null }) => b ? <span className={`bz b-${b}`}>{b}</span> : null

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

/** Complaint text with the parts the system used marked; clicking a mark says why it was marked. */
export function Marked({ text, spans }: { text: string; spans: any[] }) {
  const [sel, setSel] = useState<number | null>(null)
  if (!text) return null
  const parts: ReactNode[] = []
  let i = 0
  spans.forEach((s, n) => {
    if (s.start > i) parts.push(<span key={`t${n}`}>{text.slice(i, s.start)}</span>)
    parts.push(<mark key={`m${n}`} className={`hl ${s.kind} ${sel === n ? 'on' : ''}`} onClick={() => setSel(sel === n ? null : n)} title={s.label}>{text.slice(s.start, s.end)}</mark>)
    i = s.end
  })
  if (i < text.length) parts.push(<span key="end">{text.slice(i)}</span>)
  return (
    <div>
      <div className="complaint">{parts}</div>
      {sel !== null && spans[sel] && <div className="hl-why"><b>Why marked:</b> {spans[sel].label}</div>}
    </div>
  )
}

export function Modal({ title, children, onClose, wide }: { title: ReactNode; children: ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className={`modal ${wide ? 'wide' : ''}`} onClick={(e) => e.stopPropagation()}>
        <div className="bh"><h2>{title}</h2><button className="btn sm" onClick={onClose}>Close</button></div>
        <div style={{ padding: 14 }}>{children}</div>
      </div>
    </div>
  )
}

export const CaseLink = ({ id }: { id: string }) => <Link className="mono" to={`/case/${id}`}>{id}</Link>
export const InstLink = ({ pid, name }: { pid?: string | null; name?: string | null }) =>
  pid ? <Link to={`/institution/${pid}`}>{name || pid}</Link> : <span className="faint">Not identified</span>

export const fmtDate = (s?: string | null) => s ? new Date(s.length <= 10 ? s + 'T00:00:00' : s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
export const fmtTime = (s?: string | null) => s ? new Date(s).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'
export const pct = (n?: number | null) => n === null || n === undefined ? '—' : `${n}%`
