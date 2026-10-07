import { useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import type { Role } from '../types'

interface U { uid: number; login: string; name: string; email: string; role: Role; last_login: string | null }

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—')

export default function Users() {
  const [users, setUsers] = useState<U[]>([])
  const [error, setError] = useState('')
  const load = () => api<U[]>('/auth/users').then(setUsers).catch((e) => setError(String(e)))
  useEffect(() => { load() }, [])
  const set = async (u: U, role: Role) => {
    setError('')
    try { await api(`/auth/users/${u.uid}/role`, { method: 'PUT', json: { role } }); load() } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
  }
  return (
    <div className="panel wide">
      <h3>App roles</h3>
      <p className="muted small">
        Roles only control what this tool lets a person do. Odoo still decides which data each person can see.
        People appear here after their first sign-in; their email comes from their Odoo profile.
      </p>
      <ul className="rolelegend small">
        <li><b>Viewer</b> search, view and preview labels, make requests</li>
        <li><b>Printer</b> viewer + print, reprint, read folders, close requests</li>
        <li><b>Admin</b> printer + manage roles, add folders, email settings, see all print history</li>
      </ul>
      {error && <p className="error">{error}</p>}
      <table className="grid users">
        <thead><tr><th>Name</th><th>Odoo login</th><th>Email</th><th>Role</th><th>Last sign-in</th></tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.uid}>
              <td><b>{u.name}</b></td>
              <td>{u.login}</td>
              <td>{u.email ? <a href={`mailto:${u.email}`}>{u.email}</a> : <em className="muted">—</em>}</td>
              <td>
                <select value={u.role} onChange={(e) => set(u, e.target.value as Role)} aria-label={`Role of ${u.name}`}>
                  <option value="viewer">Viewer</option>
                  <option value="printer">Printer</option>
                  <option value="template_admin">Admin</option>
                </select>
              </td>
              <td className="nowrap">{when(u.last_login)}</td>
            </tr>
          ))}
          {!users.length && <tr><td colSpan={5} className="muted">Nobody has signed in yet.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
