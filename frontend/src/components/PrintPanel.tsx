import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ApiError, apiBlob } from '../api'
import Button from './Button'
import { ExpandIcon, XIcon } from './icons'
import type { Me, PrintItem } from '../types'

// Chrome/Edge's built-in PDF viewer honours these fragment params: no toolbar chrome, fit to the frame's width.
const VIEW_HASH = '#toolbar=0&navpanes=0&view=FitH'

export default function PrintPanel(
  { so, items, me, previewReq }: { so: string; items: PrintItem[]; me: Me; previewReq: { item: PrintItem; label: string; key: number } | null },
) {
  const [copies, setCopies] = useState(1)
  const [printer, setPrinter] = useState('')
  const [pdfUrl, setPdfUrl] = useState('')
  const [caption, setCaption] = useState('')
  const [enlarged, setEnlarged] = useState(false)
  const [busy, setBusy] = useState(false)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState('')
  const urlRef = useRef('')

  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current) }, [])
  useEffect(() => { show('', '') }, [so]) // eslint-disable-line react-hooks/exhaustive-deps

  const show = (url: string, label: string) => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = url
    setPdfUrl(url)
    setCaption(label)
    if (!url) setEnlarged(false)
  }

  const body = () => ({ so, items, copies, printer })
  const total = items.length * copies
  const canPrint = me.role !== 'viewer'

  // A row's own Preview button: fetch just that one line's label and show it here, without touching what is ticked to print.
  useEffect(() => {
    if (!previewReq) return
    let live = true
    setPreviewBusy(true); setError(''); setDone('')
    apiBlob('/print/preview', { so, items: [previewReq.item], copies: 1, printer: '' }, null)
      .then(({ blob }) => { if (live) show(URL.createObjectURL(blob), previewReq.label || 'Label preview') })
      .catch((e) => { if (live) setError(e instanceof ApiError ? e.message : String(e)) })
      .finally(() => { if (live) setPreviewBusy(false) })
    return () => { live = false }
  }, [previewReq]) // eslint-disable-line react-hooks/exhaustive-deps

  // Esc closes the enlarged view.
  useEffect(() => {
    if (!enlarged) return
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setEnlarged(false) }
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  }, [enlarged])

  const print = async () => {
    setBusy(true); setError(''); setDone('')
    try {
      const { blob, headers } = await apiBlob('/print/print', body(), 'Print job logged')
      const url = URL.createObjectURL(blob)
      show(url, `${total} label${total === 1 ? '' : 's'} · print job #${headers.get('X-Print-Job-Id')}`)
      window.open(url, '_blank')
      setDone(`Logged as print job #${headers.get('X-Print-Job-Id')} · ${headers.get('X-Label-Count')} label(s)`)
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) } finally { setBusy(false) }
  }

  return (
    <div className="panel print">
      <h3>Print</h3>
      <p className="muted small">
        {items.length
          ? `${items.length} order line${items.length === 1 ? '' : 's'} selected · ${total} label${total === 1 ? '' : 's'} (each is its PDF from the label folder)`
          : 'Click the order lines to print on the left.'}
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
        <Button variant="primary" onClick={print} disabled={busy || !items.length || !canPrint}
          title={canPrint ? '' : 'Your app role is viewer'}>Print / export</Button>
      </div>
      {error && <p className="error">{error}</p>}
      {done && <p className="ok">{done}</p>}
      {previewBusy && !pdfUrl && <p className="muted small">Loading preview…</p>}
      {pdfUrl && (
        <>
          <div className="pdfhead">
            <h4 title={caption}>{caption || 'Preview'}</h4>
            <div className="pdfhead-actions">
              <Button variant="link" onClick={() => window.open(pdfUrl, '_blank')} title="Open this PDF in a new tab">Open full size</Button>
              <Button variant="link" onClick={() => show('', '')} title="Clear the preview">Clear</Button>
            </div>
          </div>
          <div className="pdfpreview" onClick={() => setEnlarged(true)} role="button" tabIndex={0} title="Click to enlarge"
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setEnlarged(true) }}>
            <iframe title="Label preview" className="pdf" src={pdfUrl + VIEW_HASH} />
            <span className="pdfzoom"><ExpandIcon width={15} height={15} /></span>
          </div>
        </>
      )}
      {/* Rendered on <body>: inside the sticky side panel it would sit underneath the page header. */}
      {enlarged && pdfUrl && createPortal(
        <div className="pdfmodal-backdrop" onClick={() => setEnlarged(false)}>
          <div className="pdfmodal" onClick={(e) => e.stopPropagation()}>
            <div className="pdfmodal-head">
              <span title={caption}>{caption || 'Preview'}</span>
              <button type="button" className="pdfmodal-close" onClick={() => setEnlarged(false)} aria-label="Close"><XIcon width={16} height={16} /></button>
            </div>
            <iframe title="Label preview (large)" className="pdf" src={pdfUrl + VIEW_HASH} />
          </div>
        </div>,
        document.body,
      )}
    </div>
  )
}
