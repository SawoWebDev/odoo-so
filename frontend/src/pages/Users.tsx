import { useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import Button from '../components/Button'
import { CheckIcon, EyeIcon, PencilIcon, TrashIcon, XIcon } from '../components/icons'
import type { Me, Role } from '../types'

interface U {
  uid: number | null; grant_id: number | null; login: string; name: string; email: string; role: Role
  pending: boolean; main: boolean; you: boolean; last_login: string | null
  odoo_name?: string; odoo_email?: string; custom_name?: string; custom_email?: string
}

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—')

/** Admin only: who may do what in this tool. People are registered by email; the main admin can never be removed. */
export default function Users({ onViewAs }: { onViewAs: (m: Me) => void }) {
  const [users, setUsers] = useState<U[]>([])
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState<{ uid: number; name: string; email: string } | null>(null)
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
      const r = await api<{ registered: boolean; updated: boolean; login: string; role: Role }>('/auth/users', { method: 'POST', json: { email, role: 'template_admin' } })
      setMsg(r.updated ? `${r.login} is now an admin.` : `${r.login} is registered as an admin. It applies when they sign in.`)
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
  const saveDetails = () => {
    if (!editing) return
    run(async () => {
      const r = await api<{ name: string }>(`/auth/users/${editing.uid}/details`, { method: 'PUT', json: { name: editing.name, email: editing.email } })
      setMsg(`Saved: ${r.name}.`)
      setEditing(null)
    })
  }
  const viewAs = async (u: U) => {
    setBusy(true); setError('')
    try { onViewAs(await api<Me>(`/auth/users/${u.uid}/view-as`, { method: 'POST' })) }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setBusy(false) }
  }

  return (
    <div className="panel wide">
      <p className="muted small">
        <b>Admins</b> have full access. Everyone else can use the tool (search, print, requests, label files) but does not
        see <b>Settings</b>, <b>Roles</b> and the <b>Activity log</b>. Odoo still decides which data each person can see.
        <b> View as</b> shows the app as that person sees it (sales orders are still read with your own Odoo login).
      </p>

      <form className="regform" onSubmit={register}>
        <label>Register an admin
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="their Odoo login / email, e.g. name@sawo.com" required />
        </label>
        <Button type="submit" variant="primary" disabled={busy || !email.trim()}>Register as admin</Button>
      </form>
      {msg && <p className="ok">{msg}</p>}
      {error && <p className="error">{error}</p>}

      <table className="grid users">
        <thead><tr><th>Name</th><th>Odoo login</th><th>Email</th><th>Role</th><th>Last sign-in</th><th /></tr></thead>
        <tbody>
          {users.map((u) => {
            const ed = editing && editing.uid === u.uid ? editing : null
            return (
            <tr key={u.uid ?? `g${u.grant_id}`} className={ed ? 'editing' : ''}>
              <td>
                {ed ? (
                  <input value={ed.name} onChange={(e) => setEditing({ ...ed, name: e.target.value })} autoFocus
                    placeholder={u.odoo_name ? `From Odoo: ${u.odoo_name}` : 'Name'} aria-label="Name"
                    onKeyDown={(e) => { if (e.key === 'Enter') saveDetails(); if (e.key === 'Escape') setEditing(null) }} />
                ) : (
                  <>
                    {u.pending ? <em className="muted">—</em> : <b>{u.name}</b>}
                    {u.custom_name && <span className="badge" title={`Edited here. Odoo says: ${u.odoo_name || '—'}`}>edited</span>}
                    {u.main && <span className="badge status-ok">main admin</span>}{u.you && <span className="badge">you</span>}
                  </>
                )}
              </td>
              <td>{u.pending ? <em className="muted">—</em> : u.login}</td>
              <td>
                {ed ? (
                  <input type="email" value={ed.email} onChange={(e) => setEditing({ ...ed, email: e.target.value })}
                    placeholder={u.odoo_email ? `From Odoo: ${u.odoo_email}` : 'Email'} aria-label="Email"
                    onKeyDown={(e) => { if (e.key === 'Enter') saveDetails(); if (e.key === 'Escape') setEditing(null) }} />
                ) : u.email ? <a href={`mailto:${u.email}`}>{u.email}</a> : <em className="muted">—</em>}
              </td>
              <td>
                <select value={u.role === 'template_admin' ? 'template_admin' : 'printer'} disabled={busy || u.main || u.you} onChange={(e) => setUserRole(u, e.target.value as Role)} aria-label={`Role of ${u.name || u.login}`}
                  title={u.main ? 'The main admin always stays an admin' : u.you ? 'You cannot change your own role' : undefined}>
                  <option value="template_admin">Admin</option><option value="printer">User</option>
                </select>
              </td>
              <td className="nowrap">{u.pending ? <span className="muted">not signed in yet</span> : when(u.last_login)}</td>
              <td className="nowrap actionstd">
                <div className="rowactions">
                  {ed ? (
                    <>
                      <Button className="iconbtn green" disabled={busy} onClick={saveDetails} title="Save" aria-label="Save"><CheckIcon /></Button>
                      <Button className="iconbtn" disabled={busy} onClick={() => setEditing(null)} title="Cancel" aria-label="Cancel"><XIcon /></Button>
                    </>
                  ) : (
                    <>
                      {!u.pending && u.uid !== null && (
                        <Button className="iconbtn green" disabled={busy} onClick={() => setEditing({ uid: u.uid!, name: u.custom_name ?? '', email: u.custom_email ?? '' })}
                          title="Edit name and email (leave a box empty to use what Odoo says)" aria-label={`Edit ${u.name || u.login}`}><PencilIcon /></Button>
                      )}
                      {!u.pending && !u.you && (
                        <Button className="iconbtn orange" disabled={busy} onClick={() => viewAs(u)}
                          title="View as: see the app exactly as this person does. Nothing can be changed meanwhile." aria-label={`View as ${u.name || u.login}`}><EyeIcon /></Button>
                      )}
                      {!u.main && !u.you && (
                        <Button className="iconbtn red" disabled={busy} onClick={() => remove(u)}
                          title={u.pending ? 'Cancel this registration' : 'Remove from the list'} aria-label={`${u.pending ? 'Cancel registration of' : 'Remove'} ${u.name || u.login}`}><TrashIcon /></Button>
                      )}
                    </>
                  )}
                </div>
              </td>
            </tr>
            )
          })}
          {!users.length && <tr><td colSpan={6} className="muted">Nobody has signed in yet.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

