import { Fragment, useEffect, useState } from 'react'
import { ApiError, api, apiBlob } from '../api'
import Button from '../components/Button'
import type { Job, Me } from '../types'

export default function History({ me }: { me: Me }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [so, setSo] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  const load = () => api<Job[]>(`/print-jobs${so ? `?so=${encodeURIComponent(so)}` : ''}`).then(setJobs).catch((e) => setError(String(e)))
  useEffect(() => { load() }, []) // eslint-disable-line

  const reprint = async (j: Job) => {
    setError(''); setMsg('')
    try {
      const { blob, headers } = await apiBlob(`/print-jobs/${j.id}/reprint`, {}, 'Reprint logged')
      window.open(URL.createObjectURL(blob), '_blank')
      const src = headers.get('X-Reprint-Source')
      setMsg(`Reprinted job #${j.id} as #${headers.get('X-Print-Job-Id')} from the ${src === 'snapshot' ? 'files kept at print time' : 'label folder'}.`)
      load()
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
  }

  return (
    <div className="panel wide">
      <form className="searchbar" onSubmit={(e) => { e.preventDefault(); load() }}>
        <input value={so} onChange={(e) => setSo(e.target.value)} placeholder="Filter by SO number" />
        <Button type="submit">Filter</Button>
      </form>
      {error && <p className="error">{error}</p>}
      {msg && <p className="ok">{msg}</p>}
      <table className="grid">
        <thead><tr><th>#</th><th>When</th><th>SO</th><th>Labels</th><th>Copies</th><th>Printer</th><th /></tr></thead>
        <tbody>
          {jobs.map((j) => (
            <Fragment key={j.id}>
              <tr>
                <td>{j.id}{j.reprint_of ? <small className="muted"> (reprint of #{j.reprint_of})</small> : null}</td>
                <td>{j.created_at?.slice(0, 16).replace('T', ' ')}</td>
                <td>{j.so_name}</td>
                <td>{j.items.map((i) => i.code).join(', ')}</td>
                <td>{j.copies}</td><td>{j.printer}</td>
                <td>
                  <Button variant="link" onClick={() => setOpen(open === j.id ? null : j.id)}>{open === j.id ? 'Hide' : 'Files'}</Button>{' '}
                  {me.role !== 'viewer' && <Button onClick={() => reprint(j)}>Reprint</Button>}
                </td>
              </tr>
              {open === j.id && (
                <tr><td colSpan={7}>
                  <table className="calc">
                    <thead><tr><th>Item code</th><th>File used</th><th>Kept copy</th></tr></thead>
                    <tbody>
                      {j.items.map((i) => (
                        <tr key={i.line_id}><td>{i.code}</td><td>{i.path.split('/').slice(-4).join(' / ')}</td>
                          <td>{i.sha256 ? `yes (${Math.round(i.size / 1024)} KB)` : 'no - too large, reprinted from its saved location'}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </td></tr>
              )}
            </Fragment>
          ))}
          {!jobs.length && <tr><td colSpan={7} className="muted">No print jobs yet.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
