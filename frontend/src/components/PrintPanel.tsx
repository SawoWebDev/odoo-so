import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api, apiBlob, b64ToBlobUrl } from '../api'
import { toRequest } from '../selection'
import type { Me, PrintOptions, Preview, Selection, Template, Warning } from '../types'

const CALC_MODES: Record<number, string> = {
  1: '1 · Order line totals', 2: '2 · Per carton', 3: '3 · Per delivery package', 4: '4 · Editable override',
}

export const DEFAULT_OPTIONS: PrintOptions = {
  calc_mode: 1, override_base: 1, logo: false, pefc: false, copies: 1, printer: '', overrides: {},
  layout: { kind: 'native', sheet: 'A4', orientation: 'portrait', crop_marks: false, margin_mm: 0, gap_mm: 0, start_slot: 0 },
}

function WarningList({ warnings }: { warnings: Warning[] }) {
  if (!warnings.length) return null
  return (
    <ul className="warnings">
      {warnings.map((w, i) => <li key={i}>⚠ {w.message}</li>)}
    </ul>
  )
}

export default function PrintPanel({ so, selection, templates, me }: {
  so: string; selection: Selection; templates: Template[]; me: Me
}) {
  const [tid, setTid] = useState<number | ''>('')
  const [opt, setOpt] = useState<PrintOptions>(DEFAULT_OPTIONS)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [pdfUrl, setPdfUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [blocking, setBlocking] = useState<Warning[] | null>(null)
  const [done, setDone] = useState('')
  const urlRef = useRef('')

  const tpl = templates.find((t) => t.id === tid)
  const canPrint = me.role !== 'viewer'
  const hasSelection = Object.keys(selection).length > 0

  useEffect(() => { if (!tid && templates.length) setTid(templates[0].id) }, [templates, tid])
  useEffect(() => { if (tpl) setOpt((o) => ({ ...o, calc_mode: tpl.default_calc_mode })) }, [tpl?.id]) // eslint-disable-line
  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current) }, [])

  const body = (acknowledge = false) => {
    const overrides: Record<string, Record<string, string>> = {}
    for (const [k, v] of Object.entries(opt.overrides)) {
      const clean = Object.fromEntries(Object.entries(v).filter(([, x]) => x !== ''))
      if (Object.keys(clean).length) overrides[k] = clean
    }
    return {
      so, template_id: tid, selection: toRequest(selection), overrides, copies: opt.copies, layout: opt.layout,
      printer: opt.printer, acknowledge_warnings: acknowledge,
      options: { calc_mode: opt.calc_mode, override_base: opt.override_base, logo: opt.logo, pefc: opt.pefc },
    }
  }

  const show = (url: string) => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = url
    setPdfUrl(url)
  }

  const runPreview = async () => {
    setBusy(true); setError(''); setDone(''); setBlocking(null)
    try {
      const p = await api<Preview>('/render/preview', { method: 'POST', json: body() })
      setPreview(p)
      show(p.format === 'pdf' && p.pdf_base64 ? b64ToBlobUrl(p.pdf_base64) : '')
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setPreview(null) }
    finally { setBusy(false) }
  }

  const runPrint = async (acknowledge = false) => {
    setBusy(true); setError(''); setDone('')
    try {
      const { blob, headers } = await apiBlob('/render/print', body(acknowledge))
      const id = headers.get('X-Print-Job-Id')
      const status = headers.get('X-Printer-Status')
      const url = URL.createObjectURL(blob)
      if (blob.type.startsWith('application/pdf')) { show(url); window.open(url, '_blank') }
      else { const a = document.createElement('a'); a.href = url; a.download = `labels_${so}.zpl`; a.click() }
      setBlocking(null)
      setDone(`Logged as print job #${id}${status ? ` · printer: ${status}` : ''}`)
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && (e.detail as { warnings?: Warning[] })?.warnings) {
        setBlocking((e.detail as { warnings: Warning[] }).warnings)
      } else setError(e instanceof ApiError ? e.message : String(e))
    } finally { setBusy(false) }
  }

  const setOv = (label: string, field: string, v: string) =>
    setOpt((o) => ({ ...o, overrides: { ...o.overrides, [label]: { ...(o.overrides[label] ?? {}), [field]: v } } }))

  const lay = opt.layout
  const setLay = (patch: Partial<PrintOptions['layout']>) => setOpt((o) => ({ ...o, layout: { ...o.layout, ...patch } }))
  const labels = preview?.labels ?? []
  const allWarnings = useMemo(() => preview?.warnings ?? [], [preview])

  return (
    <div className="panel print">
      <h3>Print</h3>
      <label className="field">Template
        <select value={tid} onChange={(e) => { setTid(Number(e.target.value)); setPreview(null) }}>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>{t.name} · {t.size} · {t.scope}{t.active ? '' : ' (draft)'}</option>
          ))}
        </select>
      </label>
      {tpl && <p className="muted small">One label per <b>{tpl.scope}</b> · {tpl.format.toUpperCase()} · v{tpl.active_version ?? tpl.latest_version}</p>}

      <label className="field">PCS / KGS / CBM mode
        <select value={opt.calc_mode} onChange={(e) => setOpt({ ...opt, calc_mode: Number(e.target.value) })}>
          {Object.entries(CALC_MODES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      {opt.calc_mode === 4 && (
        <label className="field">Pre-fill override from
          <select value={opt.override_base} onChange={(e) => setOpt({ ...opt, override_base: Number(e.target.value) })}>
            <option value={1}>Order line totals</option><option value={2}>Per carton</option>
          </select>
        </label>
      )}
      <div className="row2">
        <label className="check"><input type="checkbox" checked={opt.logo} onChange={(e) => setOpt({ ...opt, logo: e.target.checked })} /> LOGO = YES</label>
        <label className="check"><input type="checkbox" checked={opt.pefc} onChange={(e) => setOpt({ ...opt, pefc: e.target.checked })} /> PEFC mark</label>
      </div>

      <fieldset>
        <legend>Sheet layout</legend>
        <div className="row2">
          <label className="field">Layout
            <select value={lay.kind} onChange={(e) => setLay({ kind: e.target.value, start_slot: 0 })}>
              <option value="native">Label size (no sheet)</option><option value="1up">1-up A4</option>
              <option value="2up">2-up A4</option><option value="4up">4-up A4</option>
            </select>
          </label>
          <label className="field">Copies
            <input type="number" min={1} max={500} value={opt.copies} onChange={(e) => setOpt({ ...opt, copies: Math.max(1, Number(e.target.value) || 1) })} />
          </label>
        </div>
        {lay.kind !== 'native' && (
          <>
            <div className="row2">
              <label className="field">Start at slot
                <select value={lay.start_slot} onChange={(e) => setLay({ start_slot: Number(e.target.value) })}>
                  {Array.from({ length: lay.kind === '4up' ? 4 : lay.kind === '2up' ? 2 : 1 }, (_, i) => <option key={i} value={i}>{i + 1}</option>)}
                </select>
              </label>
              <label className="check"><input type="checkbox" checked={lay.crop_marks} onChange={(e) => setLay({ crop_marks: e.target.checked })} /> Crop marks</label>
            </div>
            <div className="row2">
              <label className="field">Margin mm<input type="number" min={0} max={40} value={lay.margin_mm} onChange={(e) => setLay({ margin_mm: Number(e.target.value) })} /></label>
              <label className="field">Gap mm<input type="number" min={0} max={40} value={lay.gap_mm} onChange={(e) => setLay({ gap_mm: Number(e.target.value) })} /></label>
            </div>
          </>
        )}
      </fieldset>

      <label className="field">Printer (for the log)
        <input value={opt.printer} onChange={(e) => setOpt({ ...opt, printer: e.target.value })} placeholder="e.g. Office A4" />
      </label>

      <div className="actions">
        <button onClick={runPreview} disabled={busy || !tid || !hasSelection}>{busy ? 'Working…' : 'Preview'}</button>
        <button className="primary" onClick={() => runPrint(false)} disabled={busy || !tid || !hasSelection || !canPrint}
          title={canPrint ? '' : 'Your app role is viewer'}>Print / export</button>
      </div>
      {!hasSelection && <p className="muted small">Tick fields or rows on the left first.</p>}
      {error && <p className="error">{error}</p>}
      {done && <p className="ok">{done}</p>}

      {blocking && (
        <div className="blocking">
          <b>Check before printing</b>
          <WarningList warnings={blocking} />
          <p className="small">Fix the data in Odoo, type a value in the override boxes after previewing, or print anyway.</p>
          <button className="danger" onClick={() => runPrint(true)} disabled={busy}>Print anyway</button>
        </div>
      )}

      {preview && (
        <>
          <WarningList warnings={allWarnings} />
          {preview.render_warnings.map((w, i) => <p key={i} className="warnings">⚠ {w}</p>)}
          <p className="muted small">
            {preview.label_count} label(s){preview.info.sheets ? ` on ${preview.info.sheets} sheet(s)` : ''}
            {preview.info.empty_slots ? ` · ${preview.info.empty_slots} empty slot(s)` : ''} · {preview.template.name} v{preview.template.version}
          </p>
          <table className="calc">
            <thead><tr><th>Label</th><th>PCS</th><th>KGS</th><th>CBM</th></tr></thead>
            <tbody>
              {labels.map((l) => (
                <tr key={l.key}>
                  <th title={l.title}>{l.title.slice(0, 28)}</th>
                  {(['pcs', 'kgs', 'cbm'] as const).map((f) => (
                    <td key={f}>
                      <div className="calcval">calc: {l.calc.calculated[f] ?? <em>missing</em>}</div>
                      <input value={opt.overrides[l.key]?.[f] ?? ''} onChange={(e) => setOv(l.key, f, e.target.value)} placeholder="override" />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">Overrides change the printed label and the print log only. Nothing is written to Odoo. Press Preview again to apply.</p>
        </>
      )}
      {pdfUrl && <iframe title="Label preview" className="pdf" src={pdfUrl} />}
      {preview?.format === 'zpl' && <pre className="zpl">{preview.text}</pre>}
    </div>
  )
}
