import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import Button from '../components/Button'

interface Row { id: number; at: string | null; event: string; so: string; detail: string; uid: number | null; who: string; as: string | null }
interface Page { items: Row[]; total: number; page: number; size: number; events: string[]; people: { uid: number; name: string }[] }

const EVENT_LABEL: Record<string, string> = {
  login: 'Signed in', login_failed: 'Failed sign-in', search: 'Opened order', print: 'Printed', reprint: 'Reprinted',
  label_add: 'Added label folder', label_remove: 'Removed label folder', label_fetch: 'Rescanned folder',
  label_rescan: 'Rescanned all folders', label_delete: 'Deleted file record',
  label_request: 'Requested missing label', label_more: 'Requested additional image', label_change: 'Requested change',
  label_change_done: 'Marked request done', label_request_del: 'Deleted request',
  role_set: 'Changed role', role_register: 'Registered person', role_remove: 'Removed person',
  settings_email: 'Changed email settings', settings_email_test: 'Sent test email',
  view_as_start: 'Started viewing as', view_as_stop: 'Stopped viewing as',
}
const label = (e: string) => EVENT_LABEL[e] ?? e
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—')

/** Admin only: the audit log, newest first. */
export default function Activity() {
  const [who, setWho] = useState('')
  const [event, setEvent] = useState('')
  const [so, setSo] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Page | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async (p: number, w = who, e = event, s = so) => {
    setError('')
    const qs = new URLSearchParams({ page: String(p), size: '50' })
    if (w) qs.set('who', w)
    if (e) qs.set('event', e)
    if (s.trim()) qs.set('so', s.trim())
    try { setData(await api<Page>(`/activity?${qs}`)); setPage(p) }
    catch (err) { setError(err instanceof ApiError ? err.message : String(err)) }
  }, [who, event, so])

  useEffect(() => { load(1) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1

  return (
    <div className="panel wide">
      <form className="searchbar activityfilters" onSubmit={(e) => { e.preventDefault(); load(1) }}>
        <select value={who} onChange={(e) => { setWho(e.target.value); load(1, e.target.value) }} aria-label="Person">
          <option value="">Everyone</option>
          {data?.people.map((p) => <option key={p.uid} value={p.uid}>{p.name}</option>)}
        </select>
        <select value={event} onChange={(e) => { setEvent(e.target.value); load(1, who, e.target.value) }} aria-label="Action">
          <option value="">All actions</option>
          {data?.events.map((e) => <option key={e} value={e}>{label(e)}</option>)}
        </select>
        <input value={so} onChange={(e) => setSo(e.target.value)} placeholder="Sales order, e.g. S00123" />
        <Button type="submit">Filter</Button>
      </form>
      {error && <p className="error">{error}</p>}

      {data && (
        <>
          <p className="muted small">{data.total.toLocaleString()} entr{data.total === 1 ? 'y' : 'ies'} · page {data.page} of {pages}</p>
          <div className="tablewrap">
            <table className="grid activity">
              <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Sales order</th><th>Details</th></tr></thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id} className={r.event === 'login_failed' ? 'bad' : ''}>
                    <td className="nowrap">{when(r.at)}</td>
                    <td className="nowrap">{r.who || <em>—</em>}{r.as && <span className="badge viewas" title="An admin viewing the app as this person">as {r.as}</span>}</td>
                    <td className="nowrap">{label(r.event)}</td>
                    <td className="nowrap">{r.so || <em>—</em>}</td>
                    <td className="trunc" title={r.detail}>{r.detail || <em>—</em>}</td>
                  </tr>
                ))}
                {!data.items.length && <tr><td colSpan={5} className="muted">Nothing matches these filters.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="actions">
            <Button disabled={page <= 1} onClick={() => load(page - 1)}>&lsaquo; Prev</Button>
            <Button disabled={page >= pages} onClick={() => load(page + 1)}>Next &rsaquo;</Button>
          </div>
        </>
      )}
    </div>
  )
}
