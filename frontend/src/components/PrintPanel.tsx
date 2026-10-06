import { useEffect, useRef, useState } from 'react'
import { ApiError, apiBlob } from '../api'
import type { Me, PrintItem } from '../types'

export default function PrintPanel({ so, items, me }: { so: string; items: PrintItem[]; me: Me }) {
  const [copies, setCopies] = useState(1)
  const [printer, setPrinter] = useState('')
  const [pdfUrl, setPdfUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState('')
  const urlRef = useRef('')

  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current) }, [])
  useEffect(() => { show('') }, [so]) // eslint-disable-line react-hooks/exhaustive-deps

  const show = (url: string) => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = url
    setPdfUrl(url)
  }

  const body = () => ({ so, items, copies, printer })
  const total = items.length * copies
  const canPrint = me.role !== 'viewer'

  const preview = async () => {
    setBusy(true); setError(''); setDone('')
    try {
      const { blob } = await apiBlob('/print/preview', body())
      show(URL.createObjectURL(blob))
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) } finally { setBusy(false) }
  }

  const print = async () => {
    setBusy(true); setError(''); setDone('')
    try {
      const { blob, headers } = await apiBlob('/print/print', body())
      const url = URL.createObjectURL(blob)
      show(url)
      window.open(url, '_blank')
      setDone(`Logged as print job #${headers.get('X-Print-Job-Id')} · ${headers.get('X-Label-Count')} label(s)`)
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) } finally { setBusy(false) }
  }

  return (
    <div className="panel print">
      <h3>Print</h3>
      <p className="muted small">
        {items.length
          ? `${items.length} order line${items.length === 1 ? '' : 's'} ticked · ${total} label${total === 1 ? '' : 's'} (each is its PDF from the label folder)`
          : 'Tick the order lines to print on the left.'}
      </p>
      <div className="row2">
        <label className="field">Copies of each label
          <input type="number" min={1} max={500} value={copies} onChange={(e) => setCopies(Math.max(1, Number(e.target.value) || 1))} />
        </label>
        <label className="field">Printer (for the log)
          <input value={printer} onChange={(e) => setPrinter(e.target.value)} placeholder="e.g. Office A4" />
        </label>
      </div>
      <div className="actions">
        <button onClick={preview} disabled={busy || !items.length}>{busy ? 'Working…' : 'Preview'}</button>
        <button className="primary" onClick={print} disabled={busy || !items.length || !canPrint}
          title={canPrint ? '' : 'Your app role is viewer'}>Print / export</button>
      </div>
      {error && <p className="error">{error}</p>}
      {done && <p className="ok">{done}</p>}
      {pdfUrl && <iframe title="Label preview" className="pdf" src={pdfUrl} />}
    </div>
  )
}
