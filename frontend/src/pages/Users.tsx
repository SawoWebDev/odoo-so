import { useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import type { Role } from '../types'

interface U { uid: number; login: string; name: string; role: Role; last_login: string | null }

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
      <p className="muted small">Roles only control what this tool lets a person do (search, print, manage roles). Odoo still decides which data each person can see. People appear here after their first sign-in.</p>
      {error && <p className="error">{error}</p>}
      <table className="grid">
        <thead><tr><th>Odoo login</th><th>Name</th><th>Role</th><th>Last sign-in</th></tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.uid}>
              <td>{u.login}</td><td>{u.name}</td>
              <td>
                <select value={u.role} onChange={(e) => set(u, e.target.value as Role)}>
                  <option value="viewer">Viewer — search and view</option>
                  <option value="printer">Printer — viewer + print</option>
                  <option value="template_admin">Admin — printer + manage roles, see all print history</option>
                </select>
              </td>
              <td>{u.last_login?.slice(0, 16).replace('T', ' ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
