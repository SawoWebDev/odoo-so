import { useEffect, useState } from 'react'
import { ApiError, api } from './api'
import PageHeader from './components/PageHeader'
import Sidebar from './components/Sidebar'
import { ChevronLeftIcon, EyeIcon } from './components/icons'
import Toasts from './components/Toasts'
import Activity from './pages/Activity'
import History from './pages/History'
import Labels from './pages/Labels'
import Login from './pages/Login'
import Requests from './pages/Requests'
import Settings from './pages/Settings'
import Trace from './pages/Trace'
import Users from './pages/Users'
import { NAV, pathForTab, tabForPath, type Tab } from './nav'
import type { Me } from './types'

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [ready, setReady] = useState(false)
  const [tab, setTabState] = useState<Tab>(() => tabForPath(window.location.pathname))
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('sidebar-collapsed') === '1' } catch { return false }
  })
  const toggleCollapsed = () => setCollapsed((c) => {
    try { localStorage.setItem('sidebar-collapsed', c ? '0' : '1') } catch { /* ignore */ }
    return !c
  })

  // Navigating a tab pushes a real URL, so the browser's Back/Forward moves between pages.
  const setTab = (t: Tab) => {
    const path = pathForTab(t)
    if (window.location.pathname !== path) window.history.pushState(null, '', path)
    setTabState(t)
  }
  useEffect(() => {
    const onPop = () => setTabState(tabForPath(window.location.pathname))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

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

  const admin = me?.role === 'template_admin'

  // A non-admin who lands on an admin-only URL (bookmark, typed link) is sent back to Trace & print.
  useEffect(() => {
    if (me && !admin && NAV.find((n) => n.id === tab)?.adminOnly) setTab('trace')
  }, [me, admin, tab]) // eslint-disable-line react-hooks/exhaustive-deps

  // Switching to or from "view as" swaps who the whole app is for: start again on Trace & print.
  const switchTo = (m: Me) => { setMe(m); setTab('trace') }
  const [leaving, setLeaving] = useState(false)
  const [leaveError, setLeaveError] = useState('')
  const backToAdmin = async () => {
    setLeaving(true); setLeaveError('')
    try {
      await api<Me>('/auth/view-as/stop', { method: 'POST' })
      // A full reload, not an in-place swap: nothing loaded while viewing as them can survive into the admin's view.
      window.location.assign('/')
    } catch (e) {
      setLeaveError(e instanceof Error ? e.message : String(e))
      setLeaving(false)
    }
  }

  if (!ready) return <p className="pad">Loading…</p>
  if (!me) return <><Login onLogin={(m) => { setMe(m); setTab('trace') }} /><Toasts /></>

  const logout = async () => {
    try { await api('/auth/logout', { method: 'POST' }) } catch (e) { if (!(e instanceof ApiError)) throw e }
    setMe(null)
  }

  return (
    <div className={`app-shell${collapsed ? ' sidebar-collapsed' : ''}`}>
      <Sidebar me={me} admin={admin} tab={tab} setTab={setTab} collapsed={collapsed} onToggle={toggleCollapsed} onLogout={logout} />
      <div className="app-content">
        {me.viewing_as && (
          <div className="viewas-banner" role="status">
            <span className="viewas-text">
              <EyeIcon width={16} height={16} />
              <span>
                Viewing as <b>{me.name || me.login}</b> ({me.role === 'template_admin' ? 'Admin' : 'User'}). You see what they see;
                nothing can be printed, requested or changed in their name.
                {leaveError && <b className="viewas-error"> Could not go back: {leaveError}</b>}
              </span>
            </span>
            <button type="button" className="viewas-back" onClick={backToAdmin} disabled={leaving}>
              <ChevronLeftIcon width={16} height={16} />
              <span>{leaving ? 'Returning…' : `Back to admin (${me.viewing_as.admin_name})`}</span>
            </button>
          </div>
        )}
        <PageHeader tab={tab} />
        {/* key: a different person (view as / back) gets fresh pages, never what the previous one had loaded */}
        <main key={me.uid}>
          {/* Kept mounted (only hidden) so the search, result, chosen reference and ticks survive a visit to another tab. */}
          <div style={{ display: tab === 'trace' ? 'block' : 'none' }}><Trace me={me} active={tab === 'trace'} onGo={setTab} /></div>
          {tab === 'labels' && <Labels me={me} />}
          {tab === 'requests' && <Requests me={me} />}
          {tab === 'history' && <History me={me} />}
          {tab === 'settings' && admin && <Settings />}
          {tab === 'users' && admin && <Users onViewAs={switchTo} />}
          {tab === 'activity' && admin && <Activity />}
        </main>
      </div>
      <Toasts />
    </div>
  )
}
