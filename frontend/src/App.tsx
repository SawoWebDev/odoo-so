import { useEffect, useState } from 'react'
import { ApiError, api } from './api'
import History from './pages/History'
import Labels from './pages/Labels'
import Login from './pages/Login'
import Requests from './pages/Requests'
import Trace from './pages/Trace'
import Users from './pages/Users'
import type { Me } from './types'

type Tab = 'trace' | 'labels' | 'requests' | 'history' | 'users'

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [ready, setReady] = useState(false)
  const [tab, setTab] = useState<Tab>('trace')

  useEffect(() => {
    api<Me>('/auth/me').then(setMe).catch(() => setMe(null)).finally(() => setReady(true))
  }, [])

  // Any 401 later (idle timeout) sends the user back to the login screen.
  useEffect(() => {
    const orig = window.fetch
    window.fetch = async (...a) => {
      const r = await orig(...a)
      if (r.status === 401 && !String(a[0]).includes('/auth/')) setMe(null)
      return r
    }
    return () => { window.fetch = orig }
  }, [])

  if (!ready) return <p className="pad">Loading…</p>
  if (!me) return <Login onLogin={(m) => { setMe(m); setTab('trace') }} />

  const admin = me.role === 'template_admin'
  const logout = async () => {
    try { await api('/auth/logout', { method: 'POST' }) } catch (e) { if (!(e instanceof ApiError)) throw e }
    setMe(null)
  }

  return (
    <>
      <nav className="top">
        <strong>SO Sticker System</strong>
        <button className={tab === 'trace' ? 'on' : ''} onClick={() => setTab('trace')}>Trace &amp; print</button>
        <button className={tab === 'labels' ? 'on' : ''} onClick={() => setTab('labels')}>Label files</button>
        <button className={tab === 'requests' ? 'on' : ''} onClick={() => setTab('requests')}>Requests</button>
        <button className={tab === 'history' ? 'on' : ''} onClick={() => setTab('history')}>Print history</button>
        {admin && <button className={tab === 'users' ? 'on' : ''} onClick={() => setTab('users')}>Roles</button>}
        <span className="spacer" />
        <span className="who">{me.name} · <em>{admin ? 'admin' : me.role}</em></span>
        <button onClick={logout}>Sign out</button>
      </nav>
      <main>
        {/* Kept mounted (only hidden) so the search, result, chosen reference and ticks survive a visit to another tab. */}
        <div style={{ display: tab === 'trace' ? 'block' : 'none' }}><Trace me={me} active={tab === 'trace'} /></div>
        {tab === 'labels' && <Labels me={me} />}
        {tab === 'requests' && <Requests me={me} />}
        {tab === 'history' && <History me={me} />}
        {tab === 'users' && admin && <Users />}
      </main>
    </>
  )
}
