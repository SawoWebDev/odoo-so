import { useState } from 'react'
import { flushSync } from 'react-dom'
import { ChevronLeftIcon, LogOutIcon, MoonIcon, SunIcon } from './icons'
import { NAV, type Tab } from '../nav'
import { getTheme, toggleTheme } from '../theme'
import type { Me } from '../types'

export default function Sidebar(
  { me, admin, tab, setTab, collapsed, onToggle, onLogout }:
  { me: Me; admin: boolean; tab: Tab; setTab: (t: Tab) => void; collapsed: boolean; onToggle: () => void; onLogout: () => void },
) {
  const initial = (me.name || '?').trim().charAt(0).toUpperCase()
  const [theme, setTheme] = useState(getTheme)
  const dark = theme === 'dark'
  return (
    <aside className={`sidebar${collapsed ? ' collapsed' : ''}`}>
      <div className="sidebar-brand">
        <img src="/logo-sawo.webp" alt="SAWO" className="sidebar-logo" />
        {!collapsed && <strong>SO Sticker System</strong>}
      </div>
      <nav className="sidebar-nav">
        {NAV.filter((n) => !n.adminOnly || admin).map((n) => (
          <button
            key={n.id}
            className={`sidebar-link${tab === n.id ? ' on' : ''}`}
            onClick={() => setTab(n.id)}
            title={collapsed ? n.label : undefined}
          >
            <n.icon />
            {!collapsed && <span>{n.label}</span>}
          </button>
        ))}
      </nav>
      <button className="sidebar-collapse" onClick={onToggle} title={collapsed ? 'Expand' : 'Collapse'} aria-label="Toggle sidebar">
        <ChevronLeftIcon style={{ transform: collapsed ? 'rotate(180deg)' : undefined }} />
      </button>
      <div className="sidebar-user">
        {collapsed ? <span className="sidebar-avatar" title={me.name}>{initial}</span> : (
          <span className="sidebar-who">
            <b>{me.name}</b>
            <small>{admin ? 'Admin' : 'User'}</small>
          </span>
        )}
        <button className="sidebar-logout" onClick={onLogout} title="Sign out" aria-label="Sign out"><LogOutIcon /></button>
        {/* The button holds the pointer; only the inner face lifts and presses, so hover never flickers. */}
        <button className="sidebar-theme" onClick={(e) => toggleTheme(e.currentTarget, (t) => flushSync(() => setTheme(t)))}
          title={dark ? 'Light mode' : 'Dark mode'} aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}>
          <span className="sidebar-theme-face">
            {dark ? <SunIcon width={16} height={16} /> : <MoonIcon width={16} height={16} />}
          </span>
        </button>
      </div>
    </aside>
  )
}
