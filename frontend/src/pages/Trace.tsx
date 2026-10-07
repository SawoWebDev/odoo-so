import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api'
import OrderView from '../components/OrderView'
import PrintPanel from '../components/PrintPanel'
import { type Choice, type Picked, buildItems, prune } from '../selection'
import type { Me, Resolved } from '../types'

export default function Trace({ me, active }: { me: Me; active: boolean }) {
  const [input, setInput] = useState('')
  const [resolved, setResolved] = useState<Resolved | null>(null)
  const [picked, setPicked] = useState<Picked>([])
  const [choice, setChoice] = useState<Choice>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

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
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Sales order number, e.g. S00123" autoFocus />
          <button className="primary" disabled={busy || !input.trim()}>{busy ? 'Loading…' : 'Find SO'}</button>
          {resolved && <button type="button" onClick={() => search(resolved.so, true)} disabled={busy} title="Re-read from Odoo and re-check the label folder">↻ Refresh</button>}
        </form>
        {error && <p className="error">{error}</p>}
        {!resolved && !error && <p className="muted pad">Enter a sales order number. Each order line is matched to its label PDF by item code.</p>}
        {resolved && <OrderView key={resolved.so} resolved={resolved} onChanged={() => search(resolved.so, false, true)} picked={picked} setPicked={setPicked} choice={choice} setChoice={setChoice} />}
      </div>

      <aside className="right">
        {resolved && <PrintPanel so={resolved.so} items={buildItems(resolved, picked, choice)} me={me} />}
      </aside>
    </div>
  )
}
