import { useEffect, useState } from 'react'
import { ApiError, api, apiBlob } from '../api'
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
      const { blob, headers } = await apiBlob(`/print-jobs/${j.id}/reprint`, {})
      const url = URL.createObjectURL(blob)
      if (blob.type.startsWith('application/pdf')) window.open(url, '_blank')
      else { const a = document.createElement('a'); a.href = url; a.download = `reprint_${j.id}.zpl`; a.click() }
      setMsg(`Reprinted job #${j.id} as #${headers.get('X-Print-Job-Id')} using template version ${j.template_version} and the original values.`)
      load()
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
  }

  return (
    <div className="panel wide">
      <h3>Print history</h3>
      <form className="searchbar" onSubmit={(e) => { e.preventDefault(); load() }}>
        <input value={so} onChange={(e) => setSo(e.target.value)} placeholder="Filter by SO number" />
        <button>Filter</button>
      </form>
      {error && <p className="error">{error}</p>}
      {msg && <p className="ok">{msg}</p>}
      <table className="grid">
        <thead><tr><th>#</th><th>When</th><th>SO</th><th>Template</th><th>Copies</th><th>Layout</th><th>Printer</th><th /></tr></thead>
        <tbody>
          {jobs.map((j) => (
            <>
              <tr key={j.id}>
                <td>{j.id}{j.options.reprint_of ? <small className="muted"> (reprint of #{String(j.options.reprint_of)})</small> : null}</td>
                <td>{j.created_at?.slice(0, 16).replace('T', ' ')}</td>
                <td>{j.so_name}</td>
                <td>{j.template} <span className="badge">v{j.template_version}</span></td>
                <td>{j.copies}</td><td>{String(j.layout.kind ?? '')}</td><td>{j.printer}</td>
                <td>
                  <button className="link" onClick={() => setOpen(open === j.id ? null : j.id)}>{open === j.id ? 'Hide' : 'Details'}</button>{' '}
                  {me.role !== 'viewer' && <button onClick={() => reprint(j)}>Reprint</button>}
                </td>
              </tr>
              {open === j.id && (
                <tr key={`${j.id}d`}><td colSpan={8}>
                  <table className="calc">
                    <thead><tr><th>Label</th><th>PCS (calc → printed)</th><th>KGS</th><th>CBM</th></tr></thead>
                    <tbody>
                      {Object.entries(j.calculated).map(([k, c]) => (
                        <tr key={k}><th>{k}</th>
                          {(['pcs', 'kgs', 'cbm'] as const).map((f) => (
                            <td key={f}>{c.calculated?.[f] ?? '—'} → <b>{c.final?.[f] ?? '—'}</b>{f in (c.overrides ?? {}) ? ' (overridden)' : ''}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </td></tr>
              )}
            </>
          ))}
          {!jobs.length && <tr><td colSpan={8} className="muted">No print jobs yet.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
