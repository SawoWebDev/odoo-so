/** Pure selection-basket logic: ticking works at field, row and group level (guideline section 6). */
import type { Group, PresetRule, Resolved, Row, Selection } from './types'

export type CheckState = 'none' | 'some' | 'all'

export const selectableKeys = (row: Row): string[] => Object.keys(row.fields)

export function rowState(sel: Selection, row: Row): CheckState {
  const keys = selectableKeys(row)
  const n = keys.filter((k) => sel[row.row_id]?.includes(k)).length
  return n === 0 ? 'none' : n === keys.length ? 'all' : 'some'
}

export function groupState(sel: Selection, group: Group): CheckState {
  if (group.rows.length === 0) return 'none'
  const states = group.rows.map((r) => rowState(sel, r))
  if (states.every((s) => s === 'all')) return 'all'
  return states.every((s) => s === 'none') ? 'none' : 'some'
}

export function columnState(sel: Selection, rows: Row[], key: string): CheckState {
  const have = rows.filter((r) => key in r.fields)
  const n = have.filter((r) => sel[r.row_id]?.includes(key)).length
  return n === 0 ? 'none' : n === have.length ? 'all' : 'some'
}

function setRow(sel: Selection, row: Row, keys: string[]): Selection {
  const next = { ...sel }
  if (keys.length) next[row.row_id] = keys
  else delete next[row.row_id]
  return next
}

export function toggleCell(sel: Selection, row: Row, key: string): Selection {
  const cur = new Set(sel[row.row_id] ?? [])
  if (cur.has(key)) cur.delete(key)
  else cur.add(key)
  return setRow(sel, row, selectableKeys(row).filter((k) => cur.has(k)))
}

export function toggleRow(sel: Selection, row: Row): Selection {
  return setRow(sel, row, rowState(sel, row) === 'all' ? [] : selectableKeys(row))
}

export function toggleGroup(sel: Selection, group: Group): Selection {
  const clear = groupState(sel, group) === 'all'
  let next = sel
  for (const r of group.rows) next = setRow(next, r, clear ? [] : selectableKeys(r))
  return next
}

export function toggleColumn(sel: Selection, rows: Row[], key: string): Selection {
  const clear = columnState(sel, rows, key) === 'all'
  let next = sel
  for (const r of rows) {
    if (!(key in r.fields)) continue
    const cur = new Set(next[r.row_id] ?? [])
    if (clear) cur.delete(key)
    else cur.add(key)
    next = setRow(next, r, selectableKeys(r).filter((k) => cur.has(k)))
  }
  return next
}

export const selectedCount = (sel: Selection): number => Object.values(sel).reduce((n, k) => n + k.length, 0)

export function toRequest(sel: Selection): { items: { row: string; keys: string[] }[] } {
  return { items: Object.entries(sel).map(([row, keys]) => ({ row, keys })) }
}

/** What a basket "means" independent of one SO: per group, which fields are ticked. */
export function toPresetRules(resolved: Resolved, sel: Selection): PresetRule[] {
  const rules: PresetRule[] = []
  for (const g of resolved.groups) {
    const keys = new Set<string>()
    for (const r of g.rows) for (const k of sel[r.row_id] ?? []) keys.add(k)
    if (keys.size) rules.push({ group: g.id, keys: [...keys], rows: 'all' })
  }
  return rules
}

/** Re-apply a preset to another SO: tick those fields on every row of that group that has them. */
export function applyPreset(resolved: Resolved, rules: PresetRule[]): Selection {
  let sel: Selection = {}
  for (const rule of rules) {
    const g = resolved.groups.find((x) => x.id === rule.group)
    if (!g) continue
    for (const r of g.rows) {
      const keys = selectableKeys(r).filter((k) => rule.keys.includes(k))
      if (keys.length) sel = setRow(sel, r, keys)
    }
  }
  return sel
}

/** Selection survives a refresh of the same SO: drop rows / keys that no longer exist. */
export function pruneSelection(resolved: Resolved, sel: Selection): Selection {
  const rows = new Map(resolved.groups.flatMap((g) => g.rows).map((r) => [r.row_id, r]))
  const out: Selection = {}
  for (const [id, keys] of Object.entries(sel)) {
    const row = rows.get(id)
    if (!row) continue
    const kept = keys.filter((k) => k in row.fields)
    if (kept.length) out[id] = kept
  }
  return out
}
