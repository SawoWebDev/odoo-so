import { useEffect, useState } from 'react'
import { ApiError, api } from './api'
import History from './pages/History'
import Login from './pages/Login'
import Templates from './pages/Templates'
import Trace from './pages/Trace'
import Users from './pages/Users'
import type { Me } from './types'

type Tab = 'trace' | 'templates' | 'history' | 'users'

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
        {admin && <button className={tab === 'templates' ? 'on' : ''} onClick={() => setTab('templates')}>Templates</button>}
        <button className={tab === 'history' ? 'on' : ''} onClick={() => setTab('history')}>Print history</button>
        {admin && <button className={tab === 'users' ? 'on' : ''} onClick={() => setTab('users')}>Roles</button>}
        <span className="spacer" />
        <span className="who">{me.name} · <em>{me.role.replace('_', ' ')}</em></span>
        <button onClick={logout}>Sign out</button>
      </nav>
      <main>
        {tab === 'trace' && <Trace me={me} />}
        {tab === 'templates' && admin && <Templates />}
        {tab === 'history' && <History me={me} />}
        {tab === 'users' && admin && <Users />}
      </main>
    </>
  )
}
