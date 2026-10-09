import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api'
import { PAGE_SIZES, type PageInfo, loadPageSize, pageInfo, savePageSize } from '../paging'
import Button from './Button'
import { ChevronLeftIcon, EyeIcon, FlagIcon } from './icons'
import { type Choice, type Picked, canTick, filterRows, toggle } from '../selection'
import { KIND_LABEL, type Group, type PrintItem, type Resolved, type Row } from '../types'

const COLUMNS = ['line.product.code', 'line.product.name', 'line.qty']

/** The order header is ONE record (an SO number is unique), so it is shown as a labelled form, not as a table. */
function HeaderCard({ row, refs, active, onPick }: { row: Row; refs: Row[]; active: string | null; onPick: (id: string) => void }) {
  // Once a reference is chosen the details are rarely needed again, so the card folds to one line to give the lines room.
  const [expanded, setExpanded] = useState(false)
  const others = Object.keys(row.fields).filter((k) => k !== 'header.name' && k !== 'header.state')
  const summary = ['header.customer', 'header.customer_ref'].map((k) => row.fields[k]?.display).filter(Boolean).join(' · ')
  const refSelect = refs.length > 0 && (
    <select value={active ?? ''} onChange={(e) => e.target.value && onPick(e.target.value)} aria-label="Reference">
      <option value="" disabled>Select a reference…</option>
      {refs.map((r) => <option key={r.row_id} value={r.row_id}>{r.label}{r.fields['ref.state']?.display ? ` · ${r.fields['ref.state'].display}` : ''}</option>)}
    </select>
  )
  const toggle = active && (
    <button type="button" className="headtoggle" onClick={() => setExpanded(!expanded)}
      title={expanded ? 'Hide order details' : 'Show order details'} aria-expanded={expanded}>
      <ChevronLeftIcon width={16} height={16} style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(-90deg)' }} />
    </button>
  )

  if (active && !expanded) {
    return (
      <div className="headcard compact">
        <span className="sonum">{row.fields['header.name']?.display}</span>
        {summary && <span className="headsum" title={summary}>{summary}</span>}
        {refSelect}
        {toggle}
      </div>
    )
  }
  return (
    <div className="headcard">
      <div className="headtitle">
        <span className="caption">{row.fields['header.name']?.label}</span>
        <span className="sonum">{row.fields['header.name']?.display}</span>
        {toggle}
      </div>
      <dl className="headfields">
        {others.map((k) => (
          <div key={k} className="hf">
            <dt>{row.fields[k].label}</dt>
            <dd>{row.fields[k].display || <em>—</em>}</dd>
          </div>
        ))}
        {refSelect && (
          <div className="hf">
            <dt>Reference</dt>
            <dd>{refSelect}</dd>
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
      <Button onClick={() => onPage(1)} disabled={info.page <= 1} title="First page">&laquo;</Button>
      <Button onClick={() => onPage(info.page - 1)} disabled={info.page <= 1}>&lsaquo; Prev</Button>
      <span className="pageno">Page <b>{info.page}</b> of <b>{info.pages}</b></span>
      <Button onClick={() => onPage(info.page + 1)} disabled={info.page >= info.pages}>Next &rsaquo;</Button>
      <Button onClick={() => onPage(info.pages)} disabled={info.page >= info.pages} title="Last page">&raquo;</Button>
    </div>
  )
}

/** The saved file a row would print/preview right now: the user's choice, else the default. */
function currentFile(row: Row, choice: Choice) {
  const pdf = row.pdf
  if (!pdf || pdf.files.length === 0) return null
  const id = row.line_id as number
  const current = choice[id] ?? pdf.selected ?? pdf.files[0].id
  return pdf.files.find((x) => x.id === current) ?? pdf.files[0]
}

/** The label file(s) found for the line's item code. */
function LabelCell({ row, choice, setChoice }: { row: Row; choice: Choice; setChoice: (c: Choice) => void }) {
  const pdf = row.pdf
  if (!pdf || pdf.files.length === 0) return <span className="nopdf">No label file</span>
  const id = row.line_id as number
  const f = currentFile(row, choice)!
  const where = f.folder.split('/').slice(-2).join(' / ')
  return (
    <span className="pdfcell">
      {pdf.files.length > 1 ? (
        <select value={f.id} onChange={(e) => setChoice({ ...choice, [id]: Number(e.target.value) })} title={`${pdf.files.length} label files for ${pdf.code}`}>
          {pdf.files.map((x) => <option key={x.id} value={x.id}>{x.folder.split('/').slice(-2).join(' / ')} · {x.name}</option>)}
        </select>
      ) : (
        <span className="pdfname" title={`${f.folder}/${f.name}`}>{where && <small>{where} / </small>}{f.name}</span>
      )}
    </span>
  )
}

const stamp = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '')

/** The Actions column: a Preview button (shows this line's label on the right) and the request-a-label-file flow,
 *  plus the number of open requests for the item code (click it to read them).
 *  A request is pending until the item code has `expected` label files; it then closes by itself. */
function RequestsCell(
  { row, so, onChanged, onPreview, previewItem, previewLabel }:
  { row: Row; so: string; onChanged: () => void; onPreview: (item: PrintItem, label: string) => void; previewItem: PrintItem; previewLabel: string },
) {
  const pdf = row.pdf
  const list = pdf?.requests ?? []
  const hasFile = (pdf?.files.length ?? 0) > 0
  const missingAsked = !hasFile && !!pdf?.request
  const [open, setOpen] = useState(false)
  const [at, setAt] = useState<{ top?: number; bottom?: number; right: number }>({ right: 0 })
  const [note, setNote] = useState('')
  const [kind, setKind] = useState<'additional' | 'change'>('additional')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const anchor = useRef<HTMLElement | null>(null)
  const pop = useRef<HTMLDivElement>(null)

  const toggleOpen = (e: React.MouseEvent<HTMLElement>) => {
    anchor.current = e.currentTarget
    if (!open && anchor.current) {
      const r = anchor.current.getBoundingClientRect()
      const right = Math.max(8, window.innerWidth - r.right)
      setAt(r.bottom + 340 > window.innerHeight ? { bottom: window.innerHeight - r.top + 6, right } : { top: r.bottom + 6, right })
    }
    setOpen(!open); setErr('')
  }
  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => { if (!pop.current?.contains(e.target as Node) && !anchor.current?.contains(e.target as Node)) setOpen(false) }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    const close = () => setOpen(false)
    document.addEventListener('mousedown', away); document.addEventListener('keydown', key)
    window.addEventListener('scroll', close, true); window.addEventListener('resize', close)
    return () => {
      document.removeEventListener('mousedown', away); document.removeEventListener('keydown', key)
      window.removeEventListener('scroll', close, true); window.removeEventListener('resize', close)
    }
  }, [open])

  const send = async () => {
    setBusy(true); setErr('')
    try {
      await api('/label-requests', { method: 'POST', json: {
        code: pdf?.code ?? '', name: row.fields['line.product.name']?.display ?? '', so,
        kind: hasFile ? kind : 'missing', note: hasFile ? note : '' } })
      setNote(''); setOpen(false); onChanged()
    } catch (e) { setErr(e instanceof ApiError ? e.message : String(e)) } finally { setBusy(false) }
  }

  return (
    <>
      <td className="reqtd actionstd" onClick={(e) => e.stopPropagation()}>
        <div className="rowactions">
          <Button className="previewbtn" disabled={!hasFile} onClick={() => onPreview(previewItem, previewLabel)}
            title={hasFile ? 'Preview this label on the right' : 'No label file yet'} aria-label="Preview"><EyeIcon /></Button>
          <Button className="reqbtn" disabled={missingAsked} onClick={toggleOpen}
            title={missingAsked ? 'Already requested — this label file has been asked for' : hasFile ? 'Request an additional image or a change to this label' : 'Request this label file to be made or uploaded'}
            aria-label="Request"><FlagIcon /></Button>
        </div>
      </td>
      <td className="reqtd reqnumtd" onClick={(e) => e.stopPropagation()}>
        {list.length > 0 ? (
          <Button className="reqnum" onClick={toggleOpen}
            title={`${list.length} open request${list.length > 1 ? 's' : ''}: click to see them`}>{list.length}</Button>
        ) : (
          <span className="reqnum zero" aria-label="No open requests">0</span>  /* nothing to open: plain text, not a link */
        )}
      {open && (
        <div className="reqpop" ref={pop} style={{ top: at.top, bottom: at.bottom, right: at.right }} role="dialog" aria-label={`Requests for ${pdf?.code}`}>
          <div className="reqpop-head">
            <span className="reqpop-icon"><FlagIcon width={15} height={15} /></span>
            <div className="reqpop-title">
              <b>Request &middot; {pdf?.code}</b>
              <small>{pdf?.file_count ?? 0} label file{pdf?.file_count === 1 ? '' : 's'} saved now</small>
            </div>
            <button type="button" className="reqpop-close" onClick={() => setOpen(false)} aria-label="Close">&times;</button>
          </div>
          {list.length === 0 && <p className="muted small">No requests yet.</p>}
          {list.length > 0 && (
            <div className="reqpop-list">
              {list.map((q) => (
                <div key={q.id} className="reqitem">
                  <div className="reqitem-top">
                    <span className={`reqkind reqkind-${q.kind}`}>{KIND_LABEL[q.kind]}</span>
                    <small>{q.requested_by_name}{stamp(q.created_at) && ` · ${stamp(q.created_at)}`}</small>
                  </div>
                  {q.note && <p className="reqitem-note">{q.note}</p>}
                  <small className="wait">{q.kind === 'change' ? 'Pending: until the change is done (closed with Done on the Requests tab)' : `Pending: ${q.files_now} of ${q.expected} label files`}</small>
                </div>
              ))}
            </div>
          )}
          {hasFile ? (
            <div className="reqform">
              <b className="small">New request</b>
              <div className="reqkindpick">
                <button type="button" className={kind === 'additional' ? 'on' : ''} onClick={() => setKind('additional')}>{KIND_LABEL.additional}</button>
                <button type="button" className={kind === 'change' ? 'on' : ''} onClick={() => setKind('change')}>{KIND_LABEL.change}</button>
              </div>
              <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} autoFocus
                placeholder={kind === 'change' ? 'What has to be changed? e.g. fix the barcode, new logo…' : 'Which image do you need? e.g. a version without logo, a new size… (optional)'} />
              <Button variant="primary" onClick={send} disabled={busy || (kind === 'change' && !note.trim())}>{busy ? 'Sending request…' : 'Send request'}</Button>
            </div>
          ) : missingAsked ? null : (
            <div className="reqform"><Button variant="primary" onClick={send} disabled={busy}>{busy ? 'Requesting…' : 'Request this label file'}</Button></div>
          )}
          {err && <small className="error">{err}</small>}
        </div>
      )}
      </td>
    </>
  )
}

function LinesTable({ group, so, onChanged, picked, setPicked, choice, setChoice, onPreview, previewedLineId }: {
  group: Group; so: string; onChanged: () => void; picked: Picked; setPicked: (p: Picked) => void; choice: Choice; setChoice: (c: Choice) => void
  onPreview: (item: PrintItem, label: string) => void; previewedLineId: number | null
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
              {COLUMNS.map((k) => <th key={k}>{head?.[k]?.label ?? k}</th>)}
              <th>Label file</th>
              <th className="reqhead">Actions</th>
              <th className="reqhead reqnumhead" title="Open requests for the item code. Click a number to read them.">Req.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const on = r.line_id !== null && picked.includes(r.line_id)
              const tickable = canTick(r)
              const previewing = r.line_id !== null && r.line_id === previewedLineId
              const cls = r.disabled_kind === 'no_label' ? (r.pdf?.request ? 'requested' : 'nolabel') : r.disabled ? 'disabled' : on ? 'picked' : ''
              const rowToggle = () => { if (tickable) setPicked(toggle(picked, r)) }
              const file = currentFile(r, choice)
              const previewLabel = [r.pdf?.code, file?.name].filter(Boolean).join(' · ')
              return (
                <tr key={r.row_id} className={`${cls}${tickable ? ' rowclick' : ''}${previewing ? ' previewing' : ''}`}
                  title={r.disabled ? r.disabled_reason : tickable ? `Click to print the label for ${r.label}` : undefined} onClick={rowToggle}>
                  {COLUMNS.map((k) => {
                    const f = r.fields[k]
                    return (
                      <td key={k} className={f?.type === 'number' ? 'num' : k === 'line.product.name' ? 'trunc' : ''} title={k === 'line.product.name' ? f?.display : undefined}>
                        {f?.display || <em>—</em>}
                        {f?.uom && f.display && f.type === 'number' && <small> {f.uom}</small>}
                      </td>
                    )
                  })}
                  {/* Stops the row's click-to-toggle so opening the label-file dropdown doesn't re-render the row shut. */}
                  <td onClick={(e) => e.stopPropagation()}><LabelCell row={r} choice={choice} setChoice={setChoice} /></td>
                  <RequestsCell row={r} so={so} onChanged={onChanged} onPreview={onPreview} previewLabel={previewLabel}
                    previewItem={{ line_id: r.line_id as number, file_id: choice[r.line_id as number] ?? r.pdf?.selected ?? null }} />
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

export default function OrderView({ resolved, onChanged, picked, setPicked, choice, setChoice, onPreview, previewedLineId }: {
  resolved: Resolved; onChanged: () => void; picked: Picked; setPicked: (p: Picked) => void; choice: Choice; setChoice: (c: Choice) => void
  onPreview: (item: PrintItem, label: string) => void; previewedLineId: number | null
}) {
  const refs = resolved.groups.find((g) => g.id === 'references')
  const hasRefs = !!refs && refs.rows.length > 0
  const [active, setActive] = useState<string | null>(null)
  const chosen = hasRefs ? refs.rows.find((r) => r.row_id === active) ?? null : null
  const pick = (id: string) => { if (id !== active) { setActive(id); setPicked([]) } }  // another reference = another set of lines
  const [q, setQ] = useState('')  // search the order lines by item code and/or product name
  const visible = (g: Group): Group => (chosen ? { ...g, rows: g.rows.filter((r) => chosen.line_ids?.includes(r.line_id as number)) } : g)
  return (
    <div className="results">
      {resolved.groups.filter((g) => g.id !== 'references').map((g) => (
        <section key={g.id} className={`group st-${g.status}`}>
          <header>
            <span className="title">{g.label}</span>
            {g.id === 'lines' && g.rows.length > 0 && (!hasRefs || chosen) && <span className="count">{q.trim() ? `${filterRows(visible(g).rows, q).length} of ${visible(g).rows.length}` : visible(g).rows.length}</span>}
            {g.id === 'lines' && chosen && <span className="muted small">in {chosen.label}</span>}
            {g.status !== 'ok' && <span className={`badge status-${g.status}`} title={g.message}>{g.status.replace('_', ' ')}</span>}
            {g.id === 'lines' && g.rows.length > 0 && (!hasRefs || chosen) && (
              <span className="linesearch">
                <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search item code or product name"
                  aria-label="Search order lines" onKeyDown={(e) => { if (e.key === 'Escape') setQ('') }} />
              </span>
            )}
          </header>
          {g.rows.length === 0 && <p className="muted pad">{g.message || 'Nothing recorded for this order.'}</p>}
          {g.rows.length > 0 && g.id === 'header' && <HeaderCard row={g.rows[0]} refs={hasRefs ? refs.rows : []} active={chosen?.row_id ?? null} onPick={pick} />}
          {g.rows.length > 0 && g.id === 'lines' && hasRefs && !chosen && (
            <p className="muted pad">Select a reference in the Sales Order box above to see its order lines.</p>
          )}
          {g.rows.length > 0 && g.id === 'lines' && (!hasRefs || chosen) && (
            visible(g).rows.length === 0
              ? <p className="muted pad">No order line with an item code is moved by {chosen?.label}.</p>
              : filterRows(visible(g).rows, q).length === 0
                ? <p className="muted pad">No order line matches &ldquo;{q.trim()}&rdquo;. <Button variant="link" onClick={() => setQ('')}>Clear the search</Button></p>
                : <LinesTable key={`${chosen?.row_id ?? 'all'}|${q.trim()}`} so={resolved.so} onChanged={onChanged} group={{ ...visible(g), rows: filterRows(visible(g).rows, q) }} picked={picked} setPicked={setPicked} choice={choice} setChoice={setChoice} onPreview={onPreview} previewedLineId={previewedLineId} />
          )}
        </section>
      ))}
    </div>
  )
}
