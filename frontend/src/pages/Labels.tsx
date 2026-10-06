import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import type { LabelSearch, LabelStatus, Me } from '../types'

const EXAMPLE = 'file://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/01%20SAWO/'
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—')
const kb = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)

/** The saved list of label files (PDFs and images): where they are, and whether each is still there (red = renamed / deleted). */
export default function Labels({ me }: { me: Me }) {
  const admin = me.role === 'template_admin'
  const canCheck = me.role !== 'viewer'
  const [st, setSt] = useState<LabelStatus | null>(null)
  const [url, setUrl] = useState('')
  const [q, setQ] = useState('')
  const [only, setOnly] = useState('')
  const [page, setPage] = useState(1)
  const [res, setRes] = useState<LabelSearch | null>(null)
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  const loadFiles = useCallback(async (query: string, state: string, p: number) => {
    try { setRes(await api<LabelSearch>(`/labels/search?q=${encodeURIComponent(query)}&state=${state}&page=${p}&size=25`)) }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
  }, [])
  const loadStatus = useCallback(async () => {
    try { setSt(await api<LabelStatus>('/labels/status')) } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
  }, [])
  useEffect(() => { loadStatus(); loadFiles('', '', 1) }, [loadStatus, loadFiles])

  const run = async (name: string, fn: () => Promise<void>) => {
    setBusy(name); setError(''); setMsg('')
    try { await fn() } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) } finally { setBusy('') }
  }
  const refresh = async (p = page) => { await Promise.all([loadStatus(), loadFiles(q, only, p)]) }

  const add = () => run('add', async () => {
    const r = await api<{ result: { files: number } }>('/labels/locations', { method: 'POST', json: { url } })
    setMsg(`Folder added: ${r.result.files.toLocaleString()} label file name(s) and locations saved (PDFs and images).`)
    setUrl(''); setPage(1); await refresh(1)
  })
  const fetchNew = (id: number) => run(`fetch${id}`, async () => {
    const r = await api<{ result: { added: number; now_missing: number; restored: number } }>(`/labels/locations/${id}/fetch`, { method: 'POST' })
    setMsg(`Folder read: ${r.result.added} new file(s) saved, ${r.result.now_missing} not found any more, ${r.result.restored} found again.`)
    await refresh()
  })
  const remove = (id: number, folder: string) => {
    if (!window.confirm(`Forget this folder and its saved list?\n\n${folder}\n\nNothing on the share is deleted.`)) return
    run(`rm${id}`, async () => { await api(`/labels/locations/${id}`, { method: 'DELETE' }); setPage(1); await refresh(1) })
  }
  const rescan = () => run('rescan', async () => {
    const r = await api<{ results: { id: number; ok?: number; missing?: number; changed?: number; error?: string }[] }>('/labels/rescan', { method: 'POST' })
    const bad = r.results.filter((x) => x.error)
    const checked = r.results.reduce((n, x) => n + (x.ok ?? 0) + (x.missing ?? 0), 0)
    const gone = r.results.reduce((n, x) => n + (x.missing ?? 0), 0)
    setMsg(`Checked ${checked.toLocaleString()} saved file(s): ${gone} not found${bad.length ? `; ${bad.length} folder(s) could not be reached and were left unchanged` : ''}.`)
    if (bad.length) setError(bad.map((x) => x.error).join(' '))
    await refresh()
  })
  const del = (id: number, name: string) => {
    if (!window.confirm(`Delete the saved record of ${name}?\n\nThe file is already gone from the folder; only the record in this list is removed.`)) return
    run(`del${id}`, async () => { await api(`/labels/files/${id}`, { method: 'DELETE' }); await refresh() })
  }

  const pages = res ? Math.max(1, Math.ceil(res.total / res.size)) : 1
  const search = (e: React.FormEvent) => { e.preventDefault(); setPage(1); loadFiles(q, only, 1) }

  return (
    <div className="panel wide">
      <h3>Label files</h3>
      <p className="muted small">
        Add the folder that holds the labels. Every PDF and image (PNG, JPG, GIF, BMP, TIFF, WebP) in it and in all its sub-folders: its name and location is saved here, and printing fetches the file
        from its saved location. If a file is later renamed or deleted, its row turns <b className="redtext">red</b>.
      </p>

      {admin && (
        <form className="searchbar" onSubmit={(e) => { e.preventDefault(); add() }}>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder={EXAMPLE} />
          <button className="primary" disabled={!!busy || !url.trim()}>{busy === 'add' ? 'Reading folder…' : 'Add folder'}</button>
        </form>
      )}
      {admin && <p className="muted small">Accepts <code>file://server/share/folder</code>, <code>\\server\share\folder</code> or <code>//server/share/folder</code>; the share must be the one connected to the app.</p>}

      {st && (
        <table className="grid locs">
          <thead><tr><th>Folder</th><th>Status</th><th>Files</th><th>Not found</th><th>Last read</th><th>Last checked</th><th /></tr></thead>
          <tbody>
            {st.locations.map((l) => (
              <tr key={l.id} className={!l.reachable ? 'gone' : ''}>
                <td title={l.folder}><b>{l.url}</b></td>
                <td>{l.reachable ? <span className="badge status-ok">reachable</span> : <span className="badge status-error">cannot be reached</span>}</td>
                <td>{l.files.toLocaleString()}</td>
                <td className={l.missing ? 'redtext' : ''}>{l.missing}</td>
                <td>{when(l.last_fetched_at)}</td><td>{when(l.last_checked_at)}</td>
                <td className="nowrap">
                  {canCheck && <button disabled={!!busy} onClick={() => fetchNew(l.id)} title="Read the folder and all its sub-folders again: save every PDF and image found">{busy === `fetch${l.id}` ? 'Reading…' : 'Read folder'}</button>}{' '}
                  {admin && <button className="link" disabled={!!busy} onClick={() => remove(l.id, l.folder)}>Remove</button>}
                </td>
              </tr>
            ))}
            {!st.locations.length && <tr><td colSpan={7} className="muted">No folder added yet.{admin ? ' Paste the folder address above.' : ' Ask an admin to add it.'}</td></tr>}
          </tbody>
        </table>
      )}

      <div className="actions">
        <button onClick={rescan} disabled={!!busy || !canCheck || !st?.files}>{busy === 'rescan' ? 'Checking…' : '↻ Rescan (are the files still there?)'}</button>
        {st && <span className="muted small">{st.files.toLocaleString()} saved · {st.codes.toLocaleString()} item codes · <span className={st.missing ? 'redtext' : ''}>{st.missing} not found</span></span>}
      </div>
      {msg && <p className="ok">{msg}</p>}
      {error && <p className="error">{error}</p>}

      <form className="searchbar" onSubmit={search}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a label by item code or folder, e.g. 560-BL" />
        <select value={only} onChange={(e) => { setOnly(e.target.value); setPage(1); loadFiles(q, e.target.value, 1) }} style={{ width: 'auto' }}>
          <option value="">All files</option><option value="missing">Not found only (red)</option><option value="ok">Found only</option>
        </select>
        <button>Search</button>
      </form>
      {res && (
        <>
          <p className="muted small">{res.total.toLocaleString()} file(s) · page {res.page} of {pages}</p>
          <table className="grid files">
            <thead><tr><th>File</th><th>Location (URL)</th><th>Size</th><th>Last checked</th><th>Status</th><th title="Delete the saved record of a file that is gone">Delete</th></tr></thead>
            <tbody>
              {res.items.map((f) => (
                <tr key={f.id} className={f.status === 'missing' ? 'gone' : ''}>
                  <td><b>{f.name}</b></td><td className="path" title={f.url ?? `${f.location}/${f.folder}`}>{f.url ?? `${f.location}/${f.folder}`}</td>
                  <td>{kb(f.size)}</td><td>{when(f.last_checked)}</td>
                  <td>{f.status === 'missing' ? 'Not found' : 'OK'}</td>
                  <td className="trash">
                    {f.status === 'missing' && canCheck && (
                      <button className="icon" disabled={!!busy} onClick={() => del(f.id, f.name)} title="This file is gone: delete its saved record" aria-label={`Delete record of ${f.name}`}>🗑</button>
                    )}
                  </td>
                </tr>
              ))}
              {!res.items.length && <tr><td colSpan={6} className="muted">No matching file.</td></tr>}
            </tbody>
          </table>
          <div className="actions">
            <button disabled={page <= 1} onClick={() => { setPage(page - 1); loadFiles(q, only, page - 1) }}>&lsaquo; Prev</button>
            <button disabled={page >= pages} onClick={() => { setPage(page + 1); loadFiles(q, only, page + 1) }}>Next &rsaquo;</button>
          </div>
        </>
      )}
    </div>
  )
}
