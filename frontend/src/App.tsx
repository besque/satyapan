import { createContext, useContext, useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, getToken, setToken, type User } from './api'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Application from './pages/Application'
import Network from './pages/Network'
import Verifications from './pages/Verifications'
import EoaVerifier from './pages/EoaVerifier'
import Ledger from './pages/Ledger'
import Rules from './pages/Rules'
import Audit from './pages/Audit'
import Evaluation from './pages/Evaluation'
import Precheck from './pages/Precheck'
import MyApplications from './pages/MyApplications'

export const UserCtx = createContext<User | null>(null)
export const useUser = () => useContext(UserCtx)!

function Header({ user, onLogout }: { user: User | null; onLogout?: () => void }) {
  return <>
    <div className="topstrip"><div className="in">
      <span>Approval scrutiny &amp; document verification</span>
      {user && <span>Signed in: <b>{user.name}</b>{user.title ? ` (${user.title})` : ''} · <button onClick={onLogout}>Sign out</button></span>}
    </div></div>
    <div className="header"><div className="in">
      <div className="logo"><svg width="22" height="22" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg></div>
      <div><b>Satyapan</b><small>Application and document checking for Extension of Approval</small></div>
    </div></div>
  </>
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const nav = useNavigate()
  const { pathname } = useLocation()
  const [more, setMore] = useState(false)
  const moreOpen = more || ['/verifications', '/eoa', '/ledger', '/rules', '/audit', '/evaluation'].some((p) => pathname.startsWith(p))
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
  if (!user) return <><Header user={null} /><Login onLogin={(u) => { setUser(u); nav(u.role === 'institution' ? '/my' : '/') }} /></>
  const staff = user.role !== 'institution'
  return (
    <UserCtx.Provider value={user}>
      <Header user={user} onLogout={logout} />
      <nav className="nav"><div className="in">
        {staff ? <>
          <NavLink to="/" end>Applications</NavLink>
          <NavLink to="/network">Links between institutions</NavLink>
          <button className={`morebtn ${moreOpen ? 'active' : ''}`} onClick={() => setMore(!more)} aria-expanded={moreOpen}>More ▾</button>
        </> : <>
          <NavLink to="/my">My applications</NavLink>
          <NavLink to="/precheck">Check before submitting</NavLink>
          <NavLink to="/rules">What is checked</NavLink>
        </>}
      </div></nav>
      {staff && moreOpen && <div className="subnav"><div className="in">
        <NavLink to="/verifications">Issuer checks</NavLink>
        <NavLink to="/eoa">Check an approval letter</NavLink>
        <NavLink to="/ledger">Institution records</NavLink>
        <NavLink to="/rules">Rules</NavLink>
        <NavLink to="/audit">Activity log</NavLink>
        <NavLink to="/evaluation">Test results</NavLink>
      </div></div>}
      <main className="page">
        <Routes>
          {staff ? <>
            <Route path="/" element={<Dashboard />} />
            <Route path="/network" element={<Network />} />
            <Route path="/verifications" element={<Verifications />} />
            <Route path="/eoa" element={<EoaVerifier />} />
            <Route path="/ledger" element={<Ledger />} />
            <Route path="/ledger/:pid" element={<Ledger />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/evaluation" element={<Evaluation />} />
          </> : <>
            <Route path="/my" element={<MyApplications />} />
            <Route path="/precheck" element={<Precheck />} />
          </>}
          <Route path="/app/:id" element={<Application />} />
          <Route path="/app/:id/doc/:docId" element={<Application />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="*" element={<Navigate to={staff ? '/' : '/my'} />} />
        </Routes>
      </main>
    </UserCtx.Provider>
  )
}
