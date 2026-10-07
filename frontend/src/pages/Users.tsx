import { useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import type { Role } from '../types'

interface U {
  uid: number | null; grant_id: number | null; login: string; name: string; email: string; role: Role
  pending: boolean; main: boolean; you: boolean; last_login: string | null
}

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—')

/** Admin only: who may do what in this tool. People are registered by email; the main admin can never be removed. */
export default function Users() {
  const [users, setUsers] = useState<U[]>([])
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Role>('printer')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  const load = () => api<U[]>('/auth/users').then(setUsers).catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
  useEffect(() => { load() }, [])

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError(''); setMsg('')
    try { await fn(); await load() } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) } finally { setBusy(false) }
  }
  const register = (e: React.FormEvent) => {
    e.preventDefault()
    run(async () => {
      const r = await api<{ registered: boolean; updated: boolean; login: string; role: Role }>('/auth/users', { method: 'POST', json: { email, role } })
      setMsg(r.updated ? `${r.login} is now ${labelOf(r.role)}.` : `${r.login} is registered as ${labelOf(r.role)}. It applies when they sign in.`)
      setEmail('')
    })
  }
  const setUserRole = (u: U, r: Role) => run(async () => {
    if (u.pending) await api('/auth/users', { method: 'POST', json: { email: u.login, role: r } })
    else await api(`/auth/users/${u.uid}/role`, { method: 'PUT', json: { role: r } })
  })
  const remove = (u: U) => {
    const what = u.pending
      ? `Cancel the registration of ${u.login}?`
      : `Remove ${u.name || u.login} from the list?\n\nThey can still sign in with their Odoo login, but start again with the default role (no admin rights).`
    if (!window.confirm(what)) return
    run(async () => { await api(u.pending ? `/auth/pending/${u.grant_id}` : `/auth/users/${u.uid}`, { method: 'DELETE' }) })
  }

  return (
    <div className="panel wide">
      <h3>App roles</h3>
      <p className="muted small">
        Roles only control what this tool lets a person do. Odoo still decides which data each person can see.
        Only admins can open <b>Settings</b> and <b>Roles</b>; everyone else does not see those tabs.
      </p>
      <ul className="rolelegend small">
        <li><b>Viewer</b> search, view and preview labels, make requests</li>
        <li><b>Printer</b> viewer + print, reprint, read folders, close requests</li>
        <li><b>Admin</b> printer + manage roles, add folders, email settings, see all print history</li>
      </ul>

      <form className="regform" onSubmit={register}>
        <label>Register a person
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="their Odoo login / email, e.g. name@sawo.com" required />
        </label>
        <label>Role
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="viewer">Viewer</option><option value="printer">Printer</option><option value="template_admin">Admin</option>
          </select>
        </label>
        <button className="primary" disabled={busy || !email.trim()}>Register</button>
      </form>
      {msg && <p className="ok">{msg}</p>}
      {error && <p className="error">{error}</p>}

      <table className="grid users">
        <thead><tr><th>Name</th><th>Odoo login</th><th>Email</th><th>Role</th><th>Last sign-in</th><th /></tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.uid ?? `g${u.grant_id}`}>
              <td>{u.pending ? <em className="muted">—</em> : <b>{u.name}</b>}{u.main && <span className="badge status-ok">main admin</span>}{u.you && <span className="badge">you</span>}</td>
              <td>{u.pending ? <em className="muted">—</em> : u.login}</td>
              <td>{u.email ? <a href={`mailto:${u.email}`}>{u.email}</a> : <em className="muted">—</em>}</td>
              <td>
                <select value={u.role} disabled={busy || u.main || u.you} onChange={(e) => setUserRole(u, e.target.value as Role)} aria-label={`Role of ${u.name || u.login}`}
                  title={u.main ? 'The main admin always stays an admin' : u.you ? 'You cannot change your own role' : undefined}>
                  <option value="viewer">Viewer</option><option value="printer">Printer</option><option value="template_admin">Admin</option>
                </select>
              </td>
              <td className="nowrap">{u.pending ? <span className="muted">not signed in yet</span> : when(u.last_login)}</td>
              <td className="nowrap">
                {!u.main && !u.you && <button className="link" disabled={busy} onClick={() => remove(u)}>{u.pending ? 'Cancel' : 'Remove'}</button>}
              </td>
            </tr>
          ))}
          {!users.length && <tr><td colSpan={6} className="muted">Nobody has signed in yet.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

function labelOf(r: Role) { return r === 'template_admin' ? 'Admin' : r === 'printer' ? 'Printer' : 'Viewer' }
