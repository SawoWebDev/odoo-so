import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, form } from '../api'
import type { CatalogEntry, Mapping, Template, TemplateVersion } from '../types'

function UploadForm({ onDone }: { onDone: (t: Template) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [f, setF] = useState({ name: '', description: '', category: 'general', size: 'A6', orientation: 'portrait', scope: 'line', default_calc_mode: 1 })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return
    setBusy(true); setError('')
    try {
      onDone(await api<Template>('/templates', { method: 'POST', body: form({ file, ...f }) }))
      setFile(null)
    } catch (err) { setError(err instanceof ApiError ? err.message : String(err)) } finally { setBusy(false) }
  }
  return (
    <form className="panel" onSubmit={submit}>
      <h3>Upload a template</h3>
      <p className="muted small">
        HTML (or .zip with html + assets), Word .docx, PDF/image background as .zip with <code>fields.json</code>, or ZPL.
        Placeholders: <code>{'{{so_number}}'}</code>, <code>{'{{barcode:barcode}}'}</code>, <code>{'{{image:photo}}'}</code>,{' '}
        <code>{'{{#if pefc}}…{{/if}}'}</code>.
      </p>
      <input type="file" accept=".html,.htm,.zip,.docx,.zpl" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
      <label className="field">Name<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></label>
      <label className="field">Description<input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
      <div className="row2">
        <label className="field">Label size<input value={f.size} onChange={(e) => setF({ ...f, size: e.target.value })} placeholder="A6 or 100x150" /></label>
        <label className="field">Orientation
          <select value={f.orientation} onChange={(e) => setF({ ...f, orientation: e.target.value })}><option>portrait</option><option>landscape</option></select>
        </label>
      </div>
      <div className="row2">
        <label className="field">One label per
          <select value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value })}>
            <option value="line">order line</option><option value="so">order (SO)</option><option value="lot">lot</option><option value="package">package</option>
          </select>
        </label>
        <label className="field">Default PCS/KGS/CBM mode
          <select value={f.default_calc_mode} onChange={(e) => setF({ ...f, default_calc_mode: Number(e.target.value) })}>
            <option value={1}>1 line totals</option><option value={2}>2 per carton</option><option value={3}>3 per package</option><option value={4}>4 override</option>
          </select>
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      <button className="primary" disabled={busy || !file}>{busy ? 'Uploading…' : 'Upload (creates version 1)'}</button>
    </form>
  )
}

function Detail({ tpl, catalog, onChange }: { tpl: Template; catalog: CatalogEntry[]; onChange: (t: Template) => void }) {
  const versions = tpl.versions ?? []
  const [vid, setVid] = useState<number>(versions[versions.length - 1]?.id ?? 0)
  const v: TemplateVersion | undefined = versions.find((x) => x.id === vid) ?? versions[versions.length - 1]
  const [maps, setMaps] = useState<Mapping[]>(v?.mappings ?? [])
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [newFile, setNewFile] = useState<File | null>(null)
  useEffect(() => { setMaps(v?.mappings ?? []); setError(''); setMsg('') }, [v?.id])
  useEffect(() => { if (versions.length) setVid(versions[versions.length - 1].id) }, [versions.length])

  const run = async (fn: () => Promise<Template>, ok: string) => {
    setError(''); setMsg('')
    try { onChange(await fn()); setMsg(ok) } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
  }
  const upd = (i: number, patch: Partial<Mapping>) => setMaps(maps.map((m, j) => (j === i ? { ...m, ...patch } : m)))
  const groups = [...new Set(catalog.map((c) => c.group_label))]

  return (
    <div className="panel">
      <h3>{tpl.name} <span className={`badge ${tpl.active ? 'status-ok' : 'status-empty'}`}>{tpl.active ? `active v${tpl.active_version}` : 'draft'}</span></h3>
      <p className="muted small">{tpl.format.toUpperCase()} · {tpl.size} {tpl.orientation} · one label per {tpl.scope} · {tpl.description}</p>

      <label className="field">Version
        <select value={v?.id} onChange={(e) => setVid(Number(e.target.value))}>
          {versions.map((x) => <option key={x.id} value={x.id}>v{x.version} · {x.created_at?.slice(0, 16).replace('T', ' ')} {x.unresolved.length ? `· ${x.unresolved.length} unmapped` : ''}</option>)}
        </select>
      </label>
      {v?.findings?.length ? <p className="warnings">⚠ Removed/neutralised at render time: {v.findings.join('; ')}</p> : null}

      <table className="grid maps">
        <thead><tr><th>Placeholder</th><th>Catalog field</th><th>Overflow</th><th>Optional</th></tr></thead>
        <tbody>
          {maps.map((m, i) => (
            <tr key={m.placeholder} className={!m.optional && !m.catalog_key ? 'bad' : ''}>
              <td><code>{m.placeholder}</code> <small className="muted">{v?.placeholder_kinds?.[m.placeholder]?.join(', ')}</small></td>
              <td>
                <select value={m.catalog_key ?? ''} onChange={(e) => upd(i, { catalog_key: e.target.value || null })}>
                  <option value="">— unmapped —</option>
                  {groups.map((g) => (
                    <optgroup key={g} label={g}>
                      {catalog.filter((c) => c.group_label === g).map((c) => <option key={c.key} value={c.key}>{c.label} ({c.key})</option>)}
                    </optgroup>
                  ))}
                </select>
              </td>
              <td>
                <select value={m.overflow_rule} onChange={(e) => upd(i, { overflow_rule: e.target.value })}>
                  <option value="wrap">wrap</option><option value="shrink">shrink to fit</option><option value="truncate">truncate</option>
                </select>
              </td>
              <td><input type="checkbox" checked={m.optional} onChange={(e) => upd(i, { optional: e.target.checked })} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {error && <p className="error">{error}</p>}
      {msg && <p className="ok">{msg}</p>}
      <div className="actions">
        <button onClick={() => run(() => api<Template>(`/templates/${tpl.id}/versions`, { method: 'POST', body: form({ mappings: JSON.stringify(maps) }) }), 'Saved as a new version')}>
          Save mapping as new version
        </button>
        <button className="primary" onClick={() => run(() => api<Template>(`/templates/${tpl.id}/activate`, { method: 'POST', body: form({ version_id: v?.id }) }), `Version ${v?.version} is now active`)}>
          Activate v{v?.version}
        </button>
        {tpl.active && <button onClick={() => run(() => api<Template>(`/templates/${tpl.id}/deactivate`, { method: 'POST' }), 'Deactivated')}>Deactivate</button>}
      </div>
      <fieldset>
        <legend>Upload a new file as the next version</legend>
        <input type="file" accept=".html,.htm,.zip,.docx,.zpl" onChange={(e) => setNewFile(e.target.files?.[0] ?? null)} />
        <button disabled={!newFile} onClick={() => run(() => api<Template>(`/templates/${tpl.id}/versions`, { method: 'POST', body: form({ file: newFile }) }), 'New version created (earlier versions are kept for reprints)')}>
          Upload version
        </button>
      </fieldset>
    </div>
  )
}

export default function Templates() {
  const [list, setList] = useState<Template[]>([])
  const [catalog, setCatalog] = useState<CatalogEntry[]>([])
  const [current, setCurrent] = useState<Template | null>(null)

  const load = useCallback(async () => setList(await api<Template[]>('/templates')), [])
  useEffect(() => { load(); api<CatalogEntry[]>('/catalog').then(setCatalog) }, [load])
  const open = async (id: number) => setCurrent(await api<Template>(`/templates/${id}`))
  const changed = async (t: Template) => { setCurrent(await api<Template>(`/templates/${t.id}`)); load() }

  return (
    <div className="two-col">
      <div>
        <div className="panel">
          <h3>Template library</h3>
          <ul className="list">
            {list.map((t) => (
              <li key={t.id} className={current?.id === t.id ? 'sel' : ''}>
                <button className="link" onClick={() => open(t.id)}>{t.name}</button>
                <span className={`badge ${t.active ? 'status-ok' : 'status-empty'}`}>{t.active ? `v${t.active_version}` : 'draft'}</span>
                <small className="muted"> {t.format} · {t.size} · {t.scope}</small>
                {t.unresolved.length > 0 && <span className="badge status-error">{t.unresolved.length} unmapped</span>}
              </li>
            ))}
          </ul>
        </div>
        <UploadForm onDone={(t) => { load(); setCurrent(t) }} />
      </div>
      <div>{current ? <Detail key={current.id + ':' + (current.versions?.length ?? 0)} tpl={current} catalog={catalog} onChange={changed} /> : <p className="muted pad">Pick a template to edit its mapping and versions.</p>}</div>
    </div>
  )
}
