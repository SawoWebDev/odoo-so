import { useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import Button from '../components/Button'

interface EmailCfg {
  enabled: boolean; host: string; port: number; security: 'starttls' | 'ssl' | 'none'; username: string
  password_set: boolean; sender_name: string; sender_email: string; receivers: string[]; app_url: string
  last_status: string; last_at: string | null
}

/** Admin only: who label-request emails are sent from (SMTP account) and who receives them. */
export default function Settings() {
  const [cfg, setCfg] = useState<EmailCfg | null>(null)
  const [receivers, setReceivers] = useState('')
  const [password, setPassword] = useState('')
  const [testTo, setTestTo] = useState('')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  const apply = (c: EmailCfg) => { setCfg(c); setReceivers(c.receivers.join('\n')); setPassword('') }
  const load = () => api<EmailCfg>('/settings/email').then(apply).catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
  useEffect(() => { load() }, [])

  if (!cfg) return <div className="panel wide">{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</div>
  const set = <K extends keyof EmailCfg>(k: K, v: EmailCfg[K]) => setCfg({ ...cfg, [k]: v })

  const run = async (name: string, fn: () => Promise<void>) => {
    setBusy(name); setError(''); setMsg('')
    try { await fn() } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) } finally { setBusy('') }
  }
  const save = () => run('save', async () => {
    const c = await api<EmailCfg>('/settings/email', { method: 'PUT', json: {
      enabled: cfg.enabled, host: cfg.host, port: Number(cfg.port), security: cfg.security, username: cfg.username,
      password: password || null, sender_name: cfg.sender_name, sender_email: cfg.sender_email, receivers, app_url: cfg.app_url } })
    apply(c); setMsg('Saved.')
  })
  const test = () => run('test', async () => {
    const r = await api<{ sent_to: string[] }>('/settings/email/test', { method: 'POST', json: { to: testTo, config: {
      enabled: cfg.enabled, host: cfg.host, port: Number(cfg.port), security: cfg.security, username: cfg.username,
      password: password || null, sender_name: cfg.sender_name, sender_email: cfg.sender_email, receivers, app_url: cfg.app_url } } })
    setMsg(`Test email sent to ${r.sent_to.join(', ')}.`)
  })

  return (
    <div className="panel wide">
      <h4>Email for label requests</h4>
      <p className="muted small">
        When someone makes a label request, an email goes from the <b>sender</b> account below to every address under <b>Send to</b>.
        The email password is stored encrypted and is never shown again.
      </p>
      <label className="check"><input type="checkbox" checked={cfg.enabled} onChange={(e) => set('enabled', e.target.checked)} /> Send an email for every new label request</label>

      <fieldset className="cfg">
        <legend>Sender (SMTP account)</legend>
        <div className="cfgrow">
          <label>SMTP server<input value={cfg.host} onChange={(e) => set('host', e.target.value)} placeholder="smtp.office365.com" /></label>
          <label>Port<input type="number" value={cfg.port} onChange={(e) => set('port', Number(e.target.value))} /></label>
          <label>Security
            <select value={cfg.security} onChange={(e) => set('security', e.target.value as EmailCfg['security'])}>
              <option value="starttls">STARTTLS (port 587)</option><option value="ssl">SSL / TLS (port 465)</option><option value="none">None (port 25)</option>
            </select>
          </label>
        </div>
        <div className="cfgrow">
          <label>Username<input value={cfg.username} onChange={(e) => set('username', e.target.value)} placeholder="usually the sender email" autoComplete="off" /></label>
          <label>Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password"
              placeholder={cfg.password_set ? '•••••••• (saved; type to change)' : ''} />
          </label>
        </div>
        <div className="cfgrow">
          <label>Sender name<input value={cfg.sender_name} onChange={(e) => set('sender_name', e.target.value)} /></label>
          <label>Sender email (From)<input value={cfg.sender_email} onChange={(e) => set('sender_email', e.target.value)} placeholder="labels@yourcompany.com" /></label>
        </div>
      </fieldset>

      <fieldset className="cfg">
        <legend>Send to</legend>
        <label>Who receives the request emails (one address per line, or separated by commas). Edit and click Save.
          <textarea rows={4} value={receivers} onChange={(e) => setReceivers(e.target.value)} placeholder={'marketing@yourcompany.com\ndesign@yourcompany.com'} />
        </label>
        <label>Link to this app, shown in the email (optional)
          <input value={cfg.app_url} onChange={(e) => set('app_url', e.target.value)} placeholder="http://your-pc:8090" />
        </label>
      </fieldset>

      <div className="actions">
        <Button variant="primary" onClick={save} disabled={!!busy}>{busy === 'save' ? 'Saving…' : 'Save'}</Button>
        <input value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder="Test send to (empty = the Send to list)" style={{ maxWidth: 300 }} />
        <Button onClick={test} disabled={!!busy} title="Sends a test email with what is in the form now (no need to save first)">{busy === 'test' ? 'Sending…' : 'Send test email'}</Button>
      </div>
      {msg && <p className="ok">{msg}</p>}
      {error && <p className="error">{error}</p>}
      {cfg.last_status && (
        <p className={`small ${cfg.last_status.startsWith('FAILED') ? 'error' : 'muted'}`}>
          Last request email: {cfg.last_status}{cfg.last_at ? ` (${new Date(cfg.last_at).toLocaleString()})` : ''}
        </p>
      )}
    </div>
  )
}
