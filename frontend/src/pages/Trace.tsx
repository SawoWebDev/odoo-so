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
  // Country filter: only orders whose customer is in this country are found, and the search box suggests just those.
  const [countries, setCountries] = useState<{ id: number; name: string; code: string }[]>([])
  const [country, setCountry] = useState<number | null>(null)
  const [countryOrders, setCountryOrders] = useState<{ so: string; customer: string }[] | null>(null)
  useEffect(() => { api<typeof countries>('/countries').then(setCountries).catch(() => {}) }, [])
  useEffect(() => {
    if (!country) { setCountryOrders(null); return }
    let stale = false
    api<{ so: string; customer: string }[]>(`/so-list?country=${country}`).then((l) => { if (!stale) setCountryOrders(l) }).catch(() => {})
    return () => { stale = true }
  }, [country])
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
      const q = [refresh && 'refresh=true', country && `country=${country}`].filter(Boolean).join('&')
      const r = await api<Resolved>(`/so/${encodeURIComponent(so)}${q ? `?${q}` : ''}`)
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
            {(countryOrders?.map((o) => o.so) ?? recent).map((so) => <option key={so} value={so} />)}
          </datalist>
          {countries.length > 0 && (
            <select value={country ?? ''} onChange={(e) => setCountry(e.target.value ? Number(e.target.value) : null)} aria-label="Country" style={{ width: 'auto' }}>
              <option value="">All countries</option>
              {countries.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
            </select>
          )}
          <Button type="submit" variant="primary" disabled={busy || !input.trim()}>{busy ? 'Loading…' : 'Find SO'}</Button>
          {resolved && <Button type="button" onClick={() => search(resolved.so, true)} disabled={busy} title="Re-read from Odoo and re-check the label folder">↻ Refresh</Button>}
        </form>
        {error && <p className="error">{error}</p>}
        {country && (
          <section className="group st-ok">
            <header>
              <span className="title">Orders in {countries.find((c) => c.id === country)?.name}</span>
              {countryOrders && <span className="count">{countryOrders.length}</span>}
              <Button type="button" variant="link" onClick={() => setCountry(null)}>Clear filter</Button>
            </header>
            {!countryOrders ? <p className="muted pad">Loading…</p> : countryOrders.length === 0 ? <p className="muted pad">No sales orders for this country.</p> : (
              <div className="tablewrap" style={{ maxHeight: 260, overflow: 'auto' }}>
                <table className="grid"><tbody>
                  {countryOrders.map((o) => (
                    <tr key={o.so} className="rowclick" onClick={() => { setInput(o.so); search(o.so) }}>
                      <td><b>{o.so}</b></td><td>{o.customer}</td>
                    </tr>
                  ))}
                </tbody></table>
              </div>
            )}
          </section>
        )}
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
