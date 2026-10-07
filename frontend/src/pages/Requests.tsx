import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import type { LabelRequests, Me } from '../types'

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—')

/** Label files that were asked for. An open request closes by itself when a file for its item code is saved in
 *  Label files; the closed ones keep the link of the file that solved them. */
export default function Requests({ me }: { me: Me }) {
  const admin = me.role === 'template_admin'
  const [status, setStatus] = useState<'open' | 'solved'>('open')
  const [data, setData] = useState<LabelRequests | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async (s = status) => {
    setError('')
    try { setData(await api<LabelRequests>(`/label-requests?status=${s}`)) }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
  }, [status])
  useEffect(() => { load(status) }, [status, load])

  const done = async (id: number) => {
    setBusy(true)
    try { await api(`/label-requests/${id}/done`, { method: 'POST' }); await load() }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
    finally { setBusy(false) }
  }

  const del = async (id: number, code: string) => {
    if (!window.confirm(`Delete the request for ${code}?`)) return
    setBusy(true)
    try { await api(`/label-requests/${id}`, { method: 'DELETE' }); await load() }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
    finally { setBusy(false) }
  }

  return (
    <div className="panel wide">
      <h3>Label requests</h3>
      <p className="muted small">
        From the Trace &amp; print tab, a line with <b>no label file</b> can be requested; the request closes by itself when a label file for that
        item code is added to <b>Label files</b> (Read folder), and its link is kept under Solved. A line that <b>has</b> a label file can be
        requested too, with a note of what is needed (a change); close it with <b>Done</b> when the work is finished.
      </p>
      <div className="actions">
        <button className={status === 'open' ? 'primary' : ''} onClick={() => setStatus('open')}>Open{data ? ` (${data.counts.open})` : ''}</button>
        <button className={status === 'solved' ? 'primary' : ''} onClick={() => setStatus('solved')}>Solved{data ? ` (${data.counts.solved})` : ''}</button>
        <button onClick={() => load()} title="Check again">↻ Refresh</button>
      </div>
      {error && <p className="error">{error}</p>}
      {data && (
        <table className="grid">
          <thead>
            <tr>
              <th>Item code</th><th>Product name</th><th>Type</th><th>What is needed</th><th>Sales order</th><th>Requested by</th><th>Requested on</th>
              {status === 'solved' ? <><th>Solved on</th><th>Label file (link)</th></> : <th />}
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={r.id}>
                <td><b>{r.code}</b></td><td>{r.name || <em>—</em>}</td>
                <td>{r.kind === 'change' ? 'Change' : 'Missing label'}</td><td>{r.kind === 'change' ? r.note : <em>a label file</em>}</td><td>{r.so || <em>—</em>}</td>
                <td>{r.requested_by_name}</td><td>{when(r.created_at)}</td>
                {status === 'solved' ? (
                  <><td>{when(r.solved_at)}</td><td className="path" title={r.file_url ?? ''}>{r.kind === 'change' ? <em>done</em> : <><b>{r.file_name}</b><br />{r.file_url}</>}</td></>
                ) : (
                  <td className="nowrap">
                    {r.kind === 'change' && <button disabled={busy} onClick={() => done(r.id)} title="The change has been made">Done</button>}{' '}
                    {(admin || r.requested_by === me.uid) && <button className="link" disabled={busy} onClick={() => del(r.id, r.code)}>Delete</button>}
                  </td>
                )}
              </tr>
            ))}
            {!data.items.length && <tr><td colSpan={9} className="muted">{status === 'open' ? 'No open requests.' : 'Nothing solved yet.'}</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  )
}
