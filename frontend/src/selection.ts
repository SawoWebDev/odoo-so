/** Which order lines are ticked, and which PDF each one uses. Pure functions (unit-tested). */
import type { PrintItem, Resolved, Row } from './types'

/** Ticked line ids, in the order they were ticked (labels print in that order). */
export type Picked = number[]
/** line id -> chosen saved PDF (its id), only where the user picked something other than the default. */
export type Choice = Record<number, number>

export const lineRows = (resolved: Resolved): Row[] =>
  resolved.groups.filter((g) => g.id === 'lines').flatMap((g) => g.rows)

export const canTick = (row: Row): boolean => !row.disabled && row.line_id !== null

export function toggle(picked: Picked, row: Row): Picked {
  if (!canTick(row)) return picked
  const id = row.line_id as number
  return picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id]
}

/** After a refresh of the same SO: drop lines that vanished or can no longer be printed. */
export function prune(resolved: Resolved, picked: Picked, choice: Choice): [Picked, Choice] {
  const ok = new Map(lineRows(resolved).filter(canTick).map((r) => [r.line_id as number, r]))
  const keep = picked.filter((id) => ok.has(id))
  const kept: Choice = {}
  for (const id of keep) {
    const c = choice[id]
    if (c && ok.get(id)?.pdf?.files.some((f) => f.id === c)) kept[id] = c
  }
  return [keep, kept]
}

/** The request body items: every ticked line with the PDF to use (the chosen one, else the default). */
export function buildItems(resolved: Resolved, picked: Picked, choice: Choice): PrintItem[] {
  const rows = new Map(lineRows(resolved).map((r) => [r.line_id as number, r]))
  return picked
    .filter((id) => rows.has(id) && canTick(rows.get(id) as Row))
    .map((id) => ({ line_id: id, file_id: choice[id] ?? rows.get(id)?.pdf?.selected ?? null }))
}

/** The lines whose item code or product name contain every word typed (any case). Empty search = all lines. */
export function filterRows(rows: Row[], query: string): Row[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return rows
  return rows.filter((r) => {
    const hay = `${r.fields['line.product.code']?.display ?? ''} ${r.fields['line.product.name']?.display ?? ''}`.toLowerCase()
    return words.every((w) => hay.includes(w))
  })
}
