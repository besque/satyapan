import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, getToken, setToken, type Brand, type User } from './api'
import { fmtDate, fmtLong } from './ui'
import Login from './pages/Login'
import Home from './pages/Home'
import Applications from './pages/Applications'
import Application from './pages/Application'
import Evc from './pages/Evc'
import Compliance from './pages/Compliance'
import Item from './pages/Item'
import Institutions from './pages/Institutions'
import Institution from './pages/Institution'
import Reports from './pages/Reports'
import Alerts from './pages/Alerts'
import Rules from './pages/Rules'
import Audit from './pages/Audit'
import Evaluation from './pages/Evaluation'

export const UserCtx = createContext<User | null>(null)
export const useUser = () => useContext(UserCtx)!
type Clock = { today: string; demo: boolean; ay: string; last_date_approval: string; days_left: number }
type ClockState = { clock: Clock | null; tick: number; move: (days: number) => Promise<void> }
export const ClockCtx = createContext<ClockState>({ clock: null, tick: 0, move: async () => {} })
export const useClock = () => useContext(ClockCtx)
export const BrandCtx = createContext<Brand>({ name: '', tagline: '' })
export const useBrand = () => useContext(BrandCtx)

function Logo() {
  return <div className="logo" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round">
    <circle cx="12" cy="13" r="8" /><path d="M12 9v4l2.5 2.5M9.5 2.5h5" /></svg></div>
}

function Header({ user, onLogout }: { user: User | null; onLogout?: () => void }) {
  const brand = useBrand()
  const { clock } = useClock()
  const staff = user && user.role !== 'institution'
  return <>
    <div className="topstrip"><div className="in">
      <span>{clock && <>{fmtLong(clock.today)} · Approval cycle {clock.ay} · Last date for approval: {fmtDate(clock.last_date_approval)}</>}</span>
      {user && <span><b>{user.name}</b>{user.title ? `, ${user.title}` : ''} · <button className="lnk" onClick={onLogout}>Sign out</button></span>}
    </div></div>
    <div className="header"><div className="in">
      <Logo />
      <div><b className="brand">{brand.name}</b><small>{brand.tagline}</small></div>
      {staff && <Search />}
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
      <input placeholder="Search application no., institution or Permanent ID" value={q} onChange={(e) => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} aria-label="Search" />
      {open && r && (r.applications.length + r.institutions.length > 0) && <div className="gdrop">
        {r.applications.map((a: any) => <button key={a.id} onMouseDown={() => go(`/app/${a.id}`)}><span className="mono">{a.id}</span><span className="small faint"> {a.name}</span></button>)}
        {r.institutions.map((i: any) => <button key={i.pid} onMouseDown={() => go(`/institution/${i.pid}`)}><b>{i.name}</b><span className="small faint"> {i.city || ''} · {i.pid}{i.source === 'public' ? ' · real' : ''}</span></button>)}
      </div>}
    </div>
  )
}

function Bell() {
  const [n, setN] = useState(0)
  const loc = useLocation()
  const { tick } = useClock()
  useEffect(() => { api('/api/alerts').then((r) => setN(r.unread)).catch(() => {}) }, [loc.pathname, tick])
  return <NavLink to="/alerts" className="bell">Alerts{n > 0 && <span className="count">{n > 99 ? '99+' : n}</span>}</NavLink>
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const [brand, setBrand] = useState<Brand>({ name: '', tagline: '' })
  const [clock, setClock] = useState<Clock | null>(null)
  const [tick, setTick] = useState(0)
  const nav = useNavigate()
  useEffect(() => {
    api<Brand>('/api/brand').then((b) => { setBrand(b); document.title = `${b.name} · ${b.tagline}` }).catch(() => {})
    api<Clock>('/api/clock').then(setClock).catch(() => {})
    const as = new URLSearchParams(window.location.search).get('as')
    if (as) {
      api<{ token: string; user: User }>('/api/login', { method: 'POST', json: { user: as } })
        .then((r) => { setToken(r.token); setUser(r.user) }).catch(() => {}).finally(() => setReady(true))
      return
    }
    if (!getToken()) { setReady(true); return }
    api<User>('/api/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
  }, [])
  const move = async (n: number) => {
    const r = await api<Clock>('/api/clock', { method: 'POST', json: { days: n } })
    setClock(r)
    setTick((x) => x + 1)
  }
  if (!ready) return null
  const logout = () => { setToken(null); setUser(null); nav('/') }
  const state = { clock, tick, move }
  if (!user) return <BrandCtx.Provider value={brand}><ClockCtx.Provider value={state}><Header user={null} />
    <Login onLogin={(u) => { setUser(u); nav('/') }} /></ClockCtx.Provider></BrandCtx.Provider>
  const inst = user.role === 'institution'
  return (
    <BrandCtx.Provider value={brand}><ClockCtx.Provider value={state}><UserCtx.Provider value={user}>
      <Header user={user} onLogout={logout} />
      <nav className="nav"><div className="in">
        {inst ? <>
          <NavLink to="/" end>What you owe AICTE</NavLink>
          <NavLink to="/compliance">Undertakings and documents</NavLink>
          <span className="right"><Bell /><NavLink to="/rules">Rules</NavLink></span>
        </> : <>
          <NavLink to="/" end>{user.role === 'head' ? 'Overview' : user.role === 'admin' ? 'Overview' : 'My work'}</NavLink>
          <NavLink to="/applications">Applications</NavLink>
          <NavLink to="/evc">EVC</NavLink>
          <NavLink to="/compliance">Compliance</NavLink>
          <NavLink to="/reports">Reports</NavLink>
          <span className="right">
            <Bell />
            <NavLink to="/institutions">Institutions</NavLink>
            <NavLink to="/rules">Rules</NavLink>
            <NavLink to="/log">Activity log</NavLink>
            <NavLink to="/tests">Test results</NavLink>
          </span>
        </>}
      </div></nav>
      <main className="page" key={tick}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/app/:id" element={<Application />} />
          <Route path="/evc" element={<Evc />} />
          <Route path="/compliance" element={<Compliance />} />
          <Route path="/item/:id" element={<Item />} />
          <Route path="/institutions" element={<Institutions />} />
          <Route path="/institution/:pid" element={<Institution />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="/log" element={<Audit />} />
          <Route path="/tests" element={<Evaluation />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
      <footer className="foot"><div className="in">
        {brand.name} · {brand.tagline}. Alerts and suggestions support officers; scrutiny, inspections and decisions rest with the competent authority.
      </div></footer>
    </UserCtx.Provider></ClockCtx.Provider></BrandCtx.Provider>
  )
}
