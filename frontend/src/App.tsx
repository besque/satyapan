import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, getToken, setToken, type User } from './api'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Cases from './pages/Cases'
import Case from './pages/Case'
import Coordination from './pages/Coordination'
import Institutions from './pages/Institutions'
import Institution from './pages/Institution'
import Register from './pages/Register'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Audit from './pages/Audit'
import Evaluation from './pages/Evaluation'
import Alerts from './pages/Alerts'

export const UserCtx = createContext<User | null>(null)
export const useUser = () => useContext(UserCtx)!

function Header({ user, onLogout }: { user: User | null; onLogout?: () => void }) {
  return <>
    <div className="topstrip"><div className="in">
      <span>Institution complaint monitoring · all Bureaus and Cells</span>
      {user && <span>Signed in: <b>{user.name}</b>{user.title ? ` (${user.title})` : ''} · <button onClick={onLogout}>Sign out</button></span>}
    </div></div>
    <div className="header"><div className="in">
      <div className="logo"><svg width="22" height="22" viewBox="0 0 24 24"><circle cx="7" cy="12" r="3.2" fill="#fff" /><circle cx="17" cy="7" r="3.2" fill="#fff" /><circle cx="17" cy="17" r="3.2" fill="#fff" /><path d="M9.6 10.6 14.4 8.4M9.6 13.4l4.8 2.2" stroke="#fff" strokeWidth="1.8" /></svg></div>
      <div><b>Samanvay</b><small>One view of every complaint and action on an institution</small></div>
      {user && <Search />}
    </div></div>
  </>
}

function Search() {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [r, setR] = useState<any>(null)
  const [open, setOpen] = useState(false)
  const t = useRef<number>()
  useEffect(() => {
    window.clearTimeout(t.current)
    if (q.trim().length < 2) { setR(null); return }
    t.current = window.setTimeout(() => api(`/api/search?q=${encodeURIComponent(q)}`).then(setR).catch(() => {}), 200)
  }, [q])
  const go = (to: string) => { setOpen(false); setQ(''); nav(to) }
  return (
    <div className="gsearch" onBlur={() => setTimeout(() => setOpen(false), 150)}>
      <input placeholder="Search case no., institution or Permanent ID" value={q} onChange={(e) => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} />
      {open && r && (r.cases.length + r.institutions.length > 0) && <div className="gdrop">
        {r.institutions.map((i: any) => <button key={i.permanent_id} onMouseDown={() => go(`/institution/${i.permanent_id}`)}><b>{i.name}</b><span className="small faint"> {i.city} · {i.permanent_id}</span></button>)}
        {r.cases.map((c: any) => <button key={c.id} onMouseDown={() => go(`/case/${c.id}`)}><span className="mono">{c.id}</span><span className="small faint"> {c.institution}</span></button>)}
      </div>}
    </div>
  )
}

function Bell() {
  const [n, setN] = useState(0)
  const loc = useLocation()
  useEffect(() => { api('/api/notifications').then((r) => setN(r.unread)).catch(() => {}) }, [loc.pathname])
  return <NavLink to="/alerts" className="bell" title="Alerts">Alerts{n > 0 && <span className="count">{n > 99 ? '99+' : n}</span>}</NavLink>
}

const MORE = ['/register', '/settings', '/audit', '/evaluation']

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const nav = useNavigate()
  const { pathname } = useLocation()
  const [more, setMore] = useState(false)
  const moreOpen = more || MORE.some((p) => pathname.startsWith(p))
  useEffect(() => {
    const as = new URLSearchParams(window.location.search).get('as')
    if (as) {
      api<{ token: string; user: User }>('/api/login', { method: 'POST', json: { user: as } })
        .then((r) => { setToken(r.token); setUser(r.user) }).catch(() => {}).finally(() => setReady(true))
      return
    }
    if (!getToken()) { setReady(true); return }
    api<User>('/api/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
  }, [])
  if (!ready) return null
  const logout = () => { setToken(null); setUser(null); nav('/') }
  if (!user) return <><Header user={null} /><Login onLogin={(u) => { setUser(u); nav('/') }} /></>
  return (
    <UserCtx.Provider value={user}>
      <Header user={user} onLogout={logout} />
      <nav className="nav"><div className="in">
        <NavLink to="/" end>Overview</NavLink>
        <NavLink to="/cases">Cases</NavLink>
        <NavLink to="/coordination">Coordination</NavLink>
        <NavLink to="/institutions">Institutions</NavLink>
        <NavLink to="/reports">Reports</NavLink>
        <span className="navright">
          <Bell />
          <button className={`morebtn ${moreOpen ? 'active' : ''}`} onClick={() => setMore(!more)} aria-expanded={moreOpen}>More ▾</button>
        </span>
      </div></nav>
      {moreOpen && <div className="subnav"><div className="in">
        {(user.role === 'officer' || user.role === 'management') && <NavLink to="/register">Register complaint / import register</NavLink>}
        <NavLink to="/settings">Settings</NavLink>
        <NavLink to="/audit">Activity log</NavLink>
        <NavLink to="/evaluation">Test results</NavLink>
      </div></div>}
      <main className="page">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/cases" element={<Cases />} />
          <Route path="/case/*" element={<Case />} />
          <Route path="/coordination" element={<Coordination />} />
          <Route path="/coordination/:id" element={<Coordination />} />
          <Route path="/institutions" element={<Institutions />} />
          <Route path="/institution/:pid" element={<Institution />} />
          <Route path="/register" element={<Register />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/evaluation" element={<Evaluation />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
      <footer className="foot"><div className="in">All institutions, people and complaints shown are simulated test data. Automated alerts are advisory; actions and decisions are taken by authorised officials. <Link to="/evaluation">How well it works</Link></div></footer>
    </UserCtx.Provider>
  )
}
