import { useState } from 'react'
import { PAGE_SIZES, type PageInfo, loadPageSize, pageInfo, savePageSize } from '../paging'
import { type Choice, type Picked, canTick, toggle } from '../selection'
import type { Group, Resolved, Row } from '../types'

const COLUMNS = ['line.product.code', 'line.product.name', 'line.qty']

/** The order header is ONE record (an SO number is unique), so it is shown as a labelled form, not as a table. */
function HeaderCard({ row, refs, active, onPick }: { row: Row; refs: Row[]; active: string | null; onPick: (id: string) => void }) {
  const others = Object.keys(row.fields).filter((k) => k !== 'header.name' && k !== 'header.state')
  return (
    <div className="headcard">
      <div className="headtitle">
        <span className="caption">{row.fields['header.name']?.label}</span>
        <span className="sonum">{row.fields['header.name']?.display}</span>
      </div>
      <dl className="headfields">
        {others.map((k) => (
          <div key={k} className="hf">
            <dt>{row.fields[k].label}</dt>
            <dd>{row.fields[k].display || <em>—</em>}</dd>
          </div>
        ))}
        {refs.length > 0 && (
          <div className="hf">
            <dt>Reference</dt>
            <dd>
              <select value={active ?? ''} onChange={(e) => e.target.value && onPick(e.target.value)} aria-label="Reference">
                <option value="" disabled>Select a reference…</option>
                {refs.map((r) => <option key={r.row_id} value={r.row_id}>{r.label}{r.fields['ref.state']?.display ? ` · ${r.fields['ref.state'].display}` : ''}</option>)}
              </select>
            </dd>
          </div>
        )}
      </dl>
    </div>
  )
}

function Pager({ info, selected, onPage, onSize }: {
  info: PageInfo; selected: number; onPage: (p: number) => void; onSize: (s: number) => void
}) {
  return (
    <div className="pager">
      <span className="range">
        Showing <b>{info.from}&ndash;{info.to}</b> of <b>{info.total}</b> lines
        {selected > 0 && <> &middot; <b>{selected}</b> selected</>}
      </span>
      <span className="spacer" />
      <label className="size">Per page
        <select value={info.size} onChange={(e) => onSize(Number(e.target.value))}>
          {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      <button onClick={() => onPage(1)} disabled={info.page <= 1} title="First page">&laquo;</button>
      <button onClick={() => onPage(info.page - 1)} disabled={info.page <= 1}>&lsaquo; Prev</button>
      <span className="pageno">Page <b>{info.page}</b> of <b>{info.pages}</b></span>
      <button onClick={() => onPage(info.page + 1)} disabled={info.page >= info.pages}>Next &rsaquo;</button>
      <button onClick={() => onPage(info.pages)} disabled={info.page >= info.pages} title="Last page">&raquo;</button>
    </div>
  )
}

/** The PDF(s) found for the line's item code. */
function LabelCell({ row, choice, setChoice }: { row: Row; choice: Choice; setChoice: (c: Choice) => void }) {
  const pdf = row.pdf
  if (!pdf || pdf.files.length === 0) return <span className="nopdf">No label file</span>
  const id = row.line_id as number
  const current = choice[id] ?? pdf.selected ?? pdf.files[0].id
  const f = pdf.files.find((x) => x.id === current) ?? pdf.files[0]
  const where = f.folder.split('/').slice(-2).join(' / ')
  return (
    <span className="pdfcell">
      {pdf.files.length > 1 ? (
        <select value={current} onChange={(e) => setChoice({ ...choice, [id]: Number(e.target.value) })} title={`${pdf.files.length} label files for ${pdf.code}`}>
          {pdf.files.map((x) => <option key={x.id} value={x.id}>{x.folder.split('/').slice(-2).join(' / ')} · {x.name}</option>)}
        </select>
      ) : (
        <span className="pdfname" title={`${f.folder}/${f.name}`}>{where && <small>{where} / </small>}{f.name}</span>
      )}
    </span>
  )
}

function LinesTable({ group, picked, setPicked, choice, setChoice }: {
  group: Group; picked: Picked; setPicked: (p: Picked) => void; choice: Choice; setChoice: (c: Choice) => void
}) {
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(loadPageSize)
  const info = pageInfo(group.rows.length, page, size)
  const paged = group.rows.length > PAGE_SIZES[0]
  const rows = paged ? group.rows.slice(info.start, info.end) : group.rows
  const pager = paged && (
    <Pager info={info} selected={picked.length} onPage={setPage} onSize={(n) => { setSize(n); savePageSize(n); setPage(1) }} />
  )
  const head = group.rows[0]?.fields
  return (
    <>
      {pager}
      <div className="tablewrap">
        <table className="grid">
          <thead>
            <tr>
              <th className="rowcheck" />
              {COLUMNS.map((k) => <th key={k}>{head?.[k]?.label ?? k}</th>)}
              <th>Label file</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const on = r.line_id !== null && picked.includes(r.line_id)
              const cls = r.disabled_kind === 'no_label' ? 'nolabel' : r.disabled ? 'disabled' : on ? 'picked' : ''
              return (
                <tr key={r.row_id} className={cls} title={r.disabled ? r.disabled_reason : undefined}>
                  <th className="rowcheck">
                    <input type="checkbox" disabled={!canTick(r)} checked={on} onChange={() => setPicked(toggle(picked, r))}
                      title={r.disabled ? r.disabled_reason : `Print the label for ${r.label}`} />
                  </th>
                  {COLUMNS.map((k) => {
                    const f = r.fields[k]
                    return (
                      <td key={k} className={f?.type === 'number' ? 'num' : ''}>
                        {f?.display || <em>—</em>}
                        {f?.uom && f.display && f.type === 'number' && <small> {f.uom}</small>}
                      </td>
                    )
                  })}
                  <td><LabelCell row={r} choice={choice} setChoice={setChoice} /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {pager}
    </>
  )
}

export default function OrderView({ resolved, picked, setPicked, choice, setChoice }: {
  resolved: Resolved; picked: Picked; setPicked: (p: Picked) => void; choice: Choice; setChoice: (c: Choice) => void
}) {
  const refs = resolved.groups.find((g) => g.id === 'references')
  const hasRefs = !!refs && refs.rows.length > 0
  const [active, setActive] = useState<string | null>(null)
  const chosen = hasRefs ? refs.rows.find((r) => r.row_id === active) ?? null : null
  const pick = (id: string) => { if (id !== active) { setActive(id); setPicked([]) } }  // another reference = another set of lines
  const visible = (g: Group): Group => (chosen ? { ...g, rows: g.rows.filter((r) => chosen.line_ids?.includes(r.line_id as number)) } : g)
  return (
    <div className="results">
      {resolved.groups.filter((g) => g.id !== 'references').map((g) => (
        <section key={g.id} className={`group st-${g.status}`}>
          <header>
            <span className="title">{g.label}</span>
            {g.id === 'lines' && g.rows.length > 0 && (!hasRefs || chosen) && <span className="count">{visible(g).rows.length}</span>}
            {g.id === 'lines' && chosen && <span className="muted small">in {chosen.label}</span>}
            {g.status !== 'ok' && <span className={`badge status-${g.status}`} title={g.message}>{g.status.replace('_', ' ')}</span>}
          </header>
          {g.rows.length === 0 && <p className="muted pad">{g.message || 'Nothing recorded for this order.'}</p>}
          {g.rows.length > 0 && g.id === 'header' && <HeaderCard row={g.rows[0]} refs={hasRefs ? refs.rows : []} active={chosen?.row_id ?? null} onPick={pick} />}
          {g.rows.length > 0 && g.id === 'lines' && hasRefs && !chosen && (
            <p className="muted pad">Select a reference in the Sales Order box above to see its order lines.</p>
          )}
          {g.rows.length > 0 && g.id === 'lines' && (!hasRefs || chosen) && (
            visible(g).rows.length === 0
              ? <p className="muted pad">No order line with an item code is moved by {chosen?.label}.</p>
              : <LinesTable key={chosen?.row_id ?? 'all'} group={visible(g)} picked={picked} setPicked={setPicked} choice={choice} setChoice={setChoice} />
          )}
        </section>
      ))}
    </div>
  )
}
