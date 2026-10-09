import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Tab } from '../nav'
import type { Job, LabelRequests, LabelStatus } from '../types'

const isToday = (iso: string | null) => !!iso && new Date(iso).toDateString() === new Date().toDateString()

/** Shown on Trace & print before an order is loaded: what needs attention, and a quick way back to recent orders. */
export default function StartPanel({ recent, onOpen, onGo }: { recent: string[]; onOpen: (so: string) => void; onGo: (t: Tab) => void }) {
  const [requests, setRequests] = useState<number | null>(null)
  const [missing, setMissing] = useState<number | null>(null)
  const [jobs, setJobs] = useState<Job[] | null>(null)

  useEffect(() => {
    // Each card fills in on its own; a failed call just leaves that card showing a dash.
    api<LabelRequests>('/label-requests?status=open').then((r) => setRequests(r.counts.open)).catch(() => {})
    api<LabelStatus>('/labels/status').then((s) => setMissing(s.missing)).catch(() => {})
    api<Job[]>('/print-jobs').then(setJobs).catch(() => {})
  }, [])

  const printedToday = jobs ? jobs.filter((j) => isToday(j.created_at)).length : null
  // Before anything has been searched on this browser, offer the orders that were printed most recently instead.
  const orders = recent.length ? recent : [...new Set((jobs ?? []).map((j) => j.so_name).filter(Boolean))].slice(0, 10)

  const stats: { label: string; value: number | null; hint: string; tab: Tab; alert: boolean }[] = [
    { label: 'Open label requests', value: requests, hint: 'Waiting for a label file', tab: 'requests', alert: !!requests },
    { label: 'Label files not found', value: missing, hint: 'Renamed, moved or deleted', tab: 'labels', alert: !!missing },
    { label: 'Prints today', value: printedToday, hint: 'Print jobs logged today', tab: 'history', alert: false },
  ]

  return (
    <div className="start">
      <div className="panel recent">
        <h3>{recent.length ? 'Recent sales orders' : 'Recently printed sales orders'}</h3>
        {orders.length ? (
          <div className="recentlist">
            {orders.map((so) => (
              <button key={so} type="button" className="recentchip" onClick={() => onOpen(so)}>{so}</button>
            ))}
          </div>
        ) : (
          <p className="muted small">Orders you open will be listed here. Enter a sales order number above to start; each order line is matched to its label PDF by item code.</p>
        )}
      </div>

      <div className="statcards">
        {stats.map((s) => (
          <button key={s.label} type="button" className={`statcard${s.alert ? ' alert' : ''}`} onClick={() => onGo(s.tab)}>
            <span className="statlabel">{s.label}</span>
            <span className="statvalue">{s.value === null ? '—' : s.value.toLocaleString()}</span>
            <span className="stathint">{s.hint} &rsaquo;</span>
          </button>
        ))}
      </div>
    </div>
  )
}
