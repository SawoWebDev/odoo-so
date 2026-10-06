import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import PrintPanel from '../components/PrintPanel'
import ResultsTree from '../components/ResultsTree'
import { applyPreset, pruneSelection, selectedCount, toPresetRules } from '../selection'
import type { CatalogEntry, Me, Preset, Resolved, Selection, Template } from '../types'

export default function Trace({ me }: { me: Me }) {
  const [input, setInput] = useState('')
  const [resolved, setResolved] = useState<Resolved | null>(null)
  const [sel, setSel] = useState<Selection>({})
  const [catalog, setCatalog] = useState<CatalogEntry[]>([])
  const [templates, setTemplates] = useState<Template[]>([])
  const [presets, setPresets] = useState<Preset[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadPresets = useCallback(() => api<Preset[]>('/presets').then(setPresets).catch(() => {}), [])
  useEffect(() => {
    api<CatalogEntry[]>('/catalog').then(setCatalog).catch(() => {})
    api<Template[]>('/templates').then(setTemplates).catch(() => {})
    loadPresets()
  }, [loadPresets])

  const search = async (name = input, refresh = false) => {
    const so = name.trim()
    if (!so) return
    setBusy(true); setError('')
    try {
      const r = await api<Resolved>(`/so/${encodeURIComponent(so)}${refresh ? '?refresh=true' : ''}`)
      setSel((prev) => (resolved?.so === r.so ? pruneSelection(r, prev) : {}))
      setResolved(r)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
      if (!refresh) { setResolved(null); setSel({}) }
    } finally { setBusy(false) }
  }

  const savePreset = async () => {
    if (!resolved) return
    const name = window.prompt('Name for this preset (e.g. "Shipping label")')
    if (!name) return
    const shared = window.confirm('Share this preset with other users? (OK = shared, Cancel = only me)')
    await api('/presets', { method: 'POST', json: { name, shared, selection: { rules: toPresetRules(resolved, sel) } } })
    loadPresets()
  }

  const n = selectedCount(sel)

  return (
    <div className="trace">
      <div className="left">
        <form className="searchbar" onSubmit={(e) => { e.preventDefault(); search() }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Sales order number, e.g. S00123" autoFocus />
          <button className="primary" disabled={busy || !input.trim()}>{busy ? 'Loading…' : 'Find SO'}</button>
          {resolved && <button type="button" onClick={() => search(resolved.so, true)} disabled={busy} title="Re-read from Odoo">↻ Refresh</button>}
        </form>
        {error && <p className="error">{error}</p>}
        {!resolved && !error && <p className="muted pad">Enter a sales order number to see everything Odoo holds for it, grouped in process order.</p>}
        {resolved && (
          <>
            <div className="sobar">
              <b>{resolved.so}</b>
              <span className="muted">read from Odoo {new Date(resolved.fetched_at).toLocaleTimeString()}</span>
            </div>
            <ResultsTree resolved={resolved} sel={sel} setSel={setSel} catalog={catalog} />
          </>
        )}
      </div>

      <aside className="right">
        <div className="panel basket">
          <h3>Selection basket <span className="count">{n}</span></h3>
          <p className="muted small">{n ? `${n} field(s) in ${Object.keys(sel).length} row(s)` : 'Nothing ticked yet.'}</p>
          <div className="row2">
            <select value="" onChange={(e) => {
              const p = presets.find((x) => x.id === Number(e.target.value))
              if (p && resolved) setSel(applyPreset(resolved, p.selection.rules))
            }} disabled={!resolved || !presets.length}>
              <option value="">Apply preset…</option>
              {presets.map((p) => <option key={p.id} value={p.id}>{p.name}{p.shared ? ' (shared)' : ''}</option>)}
            </select>
            <button onClick={savePreset} disabled={!n || !resolved}>Save as preset</button>
          </div>
          <button className="link" onClick={() => setSel({})} disabled={!n}>Clear selection</button>
        </div>
        {resolved && <PrintPanel so={resolved.so} selection={sel} templates={templates} me={me} />}
      </aside>
    </div>
  )
}
