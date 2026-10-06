import { describe, expect, it } from 'vitest'
import {
  applyPreset, columnState, groupState, pruneSelection, rowState, toPresetRules, toggleCell, toggleColumn, toggleGroup,
  toggleRow, toRequest,
} from './selection'
import type { Group, Resolved, Row } from './types'

const f = (display: string) => ({ raw: display, display, type: 'text', uom: null })
const row = (id: string, keys: string[]): Row => ({
  row_id: id, label: id, scope: 'line', line_id: 1, state: '', meta: {}, fields: Object.fromEntries(keys.map((k) => [k, f(k)])),
})
const lines: Group = { id: 'lines', label: 'Order lines', status: 'ok', message: '', rows: [row('lines:1', ['a', 'b']), row('lines:2', ['a', 'b'])] }
const header: Group = { id: 'header', label: 'Header', status: 'ok', message: '', rows: [row('header:1', ['h'])] }
const resolved: Resolved = { so: 'S1', fetched_at: '', warnings: [], groups: [header, lines] }

describe('selection basket', () => {
  it('ticks a single field', () => {
    const s = toggleCell({}, lines.rows[0], 'a')
    expect(s).toEqual({ 'lines:1': ['a'] })
    expect(rowState(s, lines.rows[0])).toBe('some')
    expect(groupState(s, lines)).toBe('some')
    expect(toggleCell(s, lines.rows[0], 'a')).toEqual({})
  })

  it('ticks and clears a whole row', () => {
    const s = toggleRow({}, lines.rows[0])
    expect(rowState(s, lines.rows[0])).toBe('all')
    expect(rowState(s, lines.rows[1])).toBe('none')
    expect(toggleRow(s, lines.rows[0])).toEqual({})
    expect(toggleRow(toggleCell({}, lines.rows[0], 'a'), lines.rows[0])['lines:1']).toEqual(['a', 'b']) // partial -> all
  })

  it('ticks and clears a whole group', () => {
    const s = toggleGroup({}, lines)
    expect(groupState(s, lines)).toBe('all')
    expect(Object.keys(s)).toEqual(['lines:1', 'lines:2'])
    expect(toggleGroup(s, lines)).toEqual({})
  })

  it('ticks a column across rows', () => {
    const s = toggleColumn({}, lines.rows, 'a')
    expect(columnState(s, lines.rows, 'a')).toBe('all')
    expect(columnState(s, lines.rows, 'b')).toBe('none')
    expect(toggleColumn(s, lines.rows, 'a')).toEqual({})
  })

  it('builds the request the backend expects', () => {
    expect(toRequest({ 'lines:1': ['a', 'b'] })).toEqual({ items: [{ row: 'lines:1', keys: ['a', 'b'] }] })
  })

  it('saves a preset as rules and re-applies it to another SO', () => {
    const s = { ...toggleCell({}, lines.rows[0], 'a'), ...toggleRow({}, header.rows[0]) }
    const rules = toPresetRules(resolved, s)
    expect(rules).toEqual([{ group: 'header', keys: ['h'], rows: 'all' }, { group: 'lines', keys: ['a'], rows: 'all' }])
    const other: Resolved = { ...resolved, groups: [header, { ...lines, rows: [row('lines:9', ['a', 'b'])] }] }
    expect(applyPreset(other, rules)).toEqual({ 'header:1': ['h'], 'lines:9': ['a'] })
  })

  it('drops vanished rows and keys when the same SO is refreshed', () => {
    const next: Resolved = { ...resolved, groups: [header, { ...lines, rows: [row('lines:1', ['a'])] }] }
    expect(pruneSelection(next, { 'lines:1': ['a', 'b'], 'lines:2': ['a'], 'gone:1': ['x'] })).toEqual({ 'lines:1': ['a'] })
  })
})
