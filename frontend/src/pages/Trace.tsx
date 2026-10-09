import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api'
import Button from '../components/Button'
import OrderView from '../components/OrderView'
import PrintPanel from '../components/PrintPanel'
import StartPanel from '../components/StartPanel'
import type { Tab } from '../nav'
import { type Choice, type Picked, buildItems, prune } from '../selection'
import type { Me, PrintItem, Resolved } from '../types'

const RECENT_KEY = 'recent-so'
const RECENT_MAX = 10

const loadRecent = (): string[] => {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]') } catch { return [] }
}
const saveRecent = (so: string, prev: string[]): string[] => {
  const next = [so, ...prev.filter((x) => x.toLowerCase() !== so.toLowerCase())].slice(0, RECENT_MAX)
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)) } catch { /* ignore */ }
  return next
}

export default function Trace({ me, active, onGo }: { me: Me; active: boolean; onGo: (t: Tab) => void }) {
  const [input, setInput] = useState('')
  const [resolved, setResolved] = useState<Resolved | null>(null)
  const [picked, setPicked] = useState<Picked>([])
  const [choice, setChoice] = useState<Choice>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [recent, setRecent] = useState<string[]>(loadRecent)
  // A row's own Preview button shows just that line's label on the right; it also ticks the line, since Print / export
  // below the preview acts on whatever is ticked, and it should be ready to go for what is being previewed.
  const [previewReq, setPreviewReq] = useState<{ item: PrintItem; label: string; key: number } | null>(null)
  const requestPreview = (item: PrintItem, label: string) => {
    setPreviewReq({ item, label, key: Date.now() })
    setPicked((prev) => (prev.includes(item.line_id) ? prev : [...prev, item.line_id]))
  }

  const search = async (name = input, refresh = false, quiet = false) => {
    const so = name.trim()
    if (!so) return
    if (!quiet) setBusy(true)
    setError('')
    try {
      const r = await api<Resolved>(`/so/${encodeURIComponent(so)}${refresh ? '?refresh=true' : ''}`)
      if (resolved?.so === r.so) { const [p, c] = prune(r, picked, choice); setPicked(p); setChoice(c) }
      else { setPicked([]); setChoice({}) }
      setResolved(r)
      setRecent((prev) => saveRecent(r.so, prev))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
      if (!refresh && !quiet) { setResolved(null); setPicked([]); setChoice({}) }
    } finally { setBusy(false) }
  }

  // Coming back to this tab: quietly bring the labels / requests up to date, keeping the order, reference and ticks.
  const seen = useRef(active)
  useEffect(() => {
    if (active && !seen.current && resolved) search(resolved.so, false, true)
    seen.current = active
  }, [active]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="trace">
      <div className="left">
        <form className="searchbar" onSubmit={(e) => { e.preventDefault(); search() }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Sales order number, e.g. S00123" autoFocus
            list="recent-so" autoComplete="off" />
          <datalist id="recent-so">
            {recent.map((so) => <option key={so} value={so} />)}
          </datalist>
          <Button type="submit" variant="primary" disabled={busy || !input.trim()}>{busy ? 'Loading…' : 'Find SO'}</Button>
          {resolved && <Button type="button" onClick={() => search(resolved.so, true)} disabled={busy} title="Re-read from Odoo and re-check the label folder">↻ Refresh</Button>}
        </form>
        {error && <p className="error">{error}</p>}
        {!resolved && <StartPanel recent={recent} onOpen={(so) => { setInput(so); search(so) }} onGo={onGo} />}
        {resolved && (
          <OrderView key={resolved.so} resolved={resolved} onChanged={() => search(resolved.so, false, true)}
            picked={picked} setPicked={setPicked} choice={choice} setChoice={setChoice} onPreview={requestPreview}
            previewedLineId={previewReq?.item.line_id ?? null} />
        )}
      </div>

      <aside className="right">
        {resolved && <PrintPanel so={resolved.so} items={buildItems(resolved, picked, choice)} me={me} previewReq={previewReq} />}
      </aside>
    </div>
  )
}
