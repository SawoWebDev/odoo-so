import { describe, expect, it } from 'vitest'
import { buildItems, canTick, prune, toggle } from './selection'
import type { LabelFile, Resolved, Row } from './types'

let nextId = 100
const file = (folder: string, name = 'X.pdf'): LabelFile => ({ id: nextId++, name, folder, location_id: 1 })
const row = (id: number, over: Partial<Row> = {}, files: LabelFile[] = [file('Box')]): Row => ({
  row_id: `lines:${id}`, label: `L${id}`, line_id: id, state: '', fields: {}, disabled: false, disabled_reason: '',
  disabled_kind: '', pdf: { code: `C${id}`, files, selected: files[0]?.id ?? null, request: null, file_count: files.length, requests: [] }, ...over,
})
const resolved = (rows: Row[]): Resolved => ({
  so: 'S1', fetched_at: '', groups: [{ id: 'header', label: 'Sales Order', status: 'ok', message: '', rows: [] },
    { id: 'lines', label: 'Order lines', status: 'ok', message: '', rows }],
})

describe('ticking order lines', () => {
  it('toggles a line and remembers the order ticked', () => {
    let p = toggle([], row(2))
    p = toggle(p, row(1))
    expect(p).toEqual([2, 1])
    expect(toggle(p, row(2))).toEqual([1])
  })

  it('never ticks a greyed line (qty 0) or a line with no usable PDF (warning colour)', () => {
    const grey = row(3, { disabled: true, disabled_kind: 'no_qty', disabled_reason: 'qty 0' })
    const warn = row(4, { disabled: true, disabled_kind: 'no_label', disabled_reason: 'No label PDF' }, [])
    expect(canTick(grey)).toBe(false)
    expect(canTick(warn)).toBe(false)
    expect(toggle([], grey)).toEqual([])
    expect(toggle([1], warn)).toEqual([1])
  })
})

describe('building the print request', () => {
  const two = [file('Individual'), file('Box')]
  const only = [file('Only')]
  const r = resolved([row(1, {}, two), row(2, {}, only), row(3, { disabled: true, disabled_kind: 'no_label' }, [])])

  it('uses the default saved PDF unless another one was chosen', () => {
    expect(buildItems(r, [2, 1], {})).toEqual([{ line_id: 2, file_id: only[0].id }, { line_id: 1, file_id: two[0].id }])
    expect(buildItems(r, [1], { 1: two[1].id })).toEqual([{ line_id: 1, file_id: two[1].id }])
  })

  it('leaves out lines that cannot be printed or no longer exist', () => {
    expect(buildItems(r, [3, 99, 1], {})).toEqual([{ line_id: 1, file_id: two[0].id }])
  })
})

describe('refreshing the same order', () => {
  it('drops vanished and no-longer-printable lines and stale PDF choices', () => {
    const files = [file('Individual'), file('Box')]
    const next = resolved([row(1, {}, files), row(2, { disabled: true, disabled_kind: 'no_label' }, [])])
    expect(prune(next, [1, 2, 7], { 1: files[1].id, 2: 5, 7: 6 })).toEqual([[1], { 1: files[1].id }])
    expect(prune(next, [1], { 1: 99999 })).toEqual([[1], {}])  // that PDF was deleted from the saved list
  })
})
