import { useState } from 'react'
import { ApiError, api } from '../api'
import Button from '../components/Button'
import type { Me } from '../types'

export default function Login({ onLogin }: { onLogin: (m: Me) => void }) {
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      onLogin(await api<Me>('/auth/login', { method: 'POST', json: { login, password } }))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Cannot reach the server')
    } finally { setBusy(false); setPassword('') }
  }

  return (
    <div className="login">
      <form onSubmit={submit} className="panel">
        <h1>SO Sticker System</h1>
        <p className="muted">Sign in with your Odoo account. Odoo decides what you can see.</p>
        <label className="field">Odoo login
          <input value={login} onChange={(e) => setLogin(e.target.value)} autoComplete="username" autoFocus required />
        </label>
        <label className="field">Odoo password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error && <p className="error">{error}</p>}
        <Button type="submit" variant="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</Button>
        <p className="muted small">Read-only: this tool never writes to Odoo. Your password is kept encrypted in a short-lived server session and is never stored.</p>
      </form>
    </div>
  )
}
