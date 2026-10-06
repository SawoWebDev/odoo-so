import { useEffect, useRef, useState } from 'react'
import type { CatalogEntry, Group, Resolved, Row, Selection } from '../types'
import {
  type CheckState, columnState, groupState, rowState, toggleCell, toggleColumn, toggleGroup, toggleRow,
} from '../selection'

export function Tri({ state, onChange, title }: { state: CheckState; onChange: () => void; title?: string }) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { if (ref.current) ref.current.indeterminate = state === 'some' }, [state])
  return <input ref={ref} type="checkbox" checked={state === 'all'} onChange={onChange} title={title} />
}

const STATUS_TEXT: Record<Group['status'], string> = {
  ok: '', empty: 'none', not_accessible: 'not accessible', not_installed: 'module not installed', error: 'error',
}

/** Rows of one group, split into tables by row kind ("lines", "mrp_wo", ...) because kinds have different columns. */
function kinds(rows: Row[]): Map<string, Row[]> {
  const m = new Map<string, Row[]>()
  for (const r of rows) {
    const k = r.row_id.split(':')[0]
    m.set(k, [...(m.get(k) ?? []), r])
  }
  return m
}

function KindTable({ rows, sel, setSel, cat }: {
  rows: Row[]; sel: Selection; setSel: (s: Selection) => void; cat: Map<string, CatalogEntry>
}) {
  const keys: string[] = []
  for (const r of rows) for (const k of Object.keys(r.fields)) if (!keys.includes(k)) keys.push(k)
  return (
    <div className="tablewrap">
      <table className="grid">
        <thead>
          <tr>
            <th className="rowhead" />
            {keys.map((k) => (
              <th key={k}>
                <label className="colhead" title={`Tick "${cat.get(k)?.label ?? k}" on every row`}>
                  <Tri state={columnState(sel, rows, k)} onChange={() => setSel(toggleColumn(sel, rows, k))} />
                  {cat.get(k)?.label ?? k}
                </label>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.row_id} className={rowState(sel, r) !== 'none' ? 'picked' : ''}>
              <th className="rowhead">
                <label>
                  <Tri state={rowState(sel, r)} onChange={() => setSel(toggleRow(sel, r))} title="Tick the whole row" />
                  <span className="rowlabel">{r.label}</span>
                  {r.state && <span className={`badge st-${r.state}`}>{r.state}</span>}
                </label>
              </th>
              {keys.map((k) => {
                const f = r.fields[k]
                if (!f) return <td key={k} className="na" />
                const on = sel[r.row_id]?.includes(k) ?? false
                return (
                  <td key={k} className={on ? 'on' : ''}>
                    <label className="cell">
                      <input type="checkbox" checked={on} onChange={() => setSel(toggleCell(sel, r, k))} />
                      <span className={f.type === 'number' ? 'num' : ''}>
                        {f.display || <em>—</em>}
                        {f.uom && f.display && f.type === 'number' && <small> {f.uom}</small>}
                      </span>
                    </label>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function ResultsTree({ resolved, sel, setSel, catalog }: {
  resolved: Resolved; sel: Selection; setSel: (s: Selection) => void; catalog: CatalogEntry[]
}) {
  const cat = new Map(catalog.map((c) => [c.key, c]))
  const [open, setOpen] = useState<Record<string, boolean>>({ header: true, lines: true, delivery: true })
  return (
    <div className="results">
      {resolved.groups.map((g, i) => {
        const usable = g.rows.length > 0
        const isOpen = open[g.id] ?? false
        return (
          <section key={g.id} className={`group st-${g.status}`}>
            <header>
              <span className="step">{i + 1}</span>
              <Tri state={groupState(sel, g)} onChange={() => usable && setSel(toggleGroup(sel, g))} title="Tick the whole group" />
              <button className="link" onClick={() => setOpen({ ...open, [g.id]: !isOpen })}>
                {isOpen ? '▾' : '▸'} {g.label}
              </button>
              <span className="count">{usable ? `${g.rows.length}` : ''}</span>
              {g.status !== 'ok' && <span className={`badge status-${g.status}`} title={g.message}>{STATUS_TEXT[g.status]}</span>}
            </header>
            {isOpen && usable && [...kinds(g.rows)].map(([k, rows]) => (
              <KindTable key={k} rows={rows} sel={sel} setSel={setSel} cat={cat} />
            ))}
            {isOpen && !usable && <p className="muted pad">{g.message || 'Nothing recorded for this order.'}</p>}
          </section>
        )
      })}
    </div>
  )
}
