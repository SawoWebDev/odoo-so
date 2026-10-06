/** Pure pagination maths (the data is already loaded; pages only change what is drawn). */
export const PAGE_SIZES = [10, 25, 50, 100]
export const DEFAULT_PAGE_SIZE = 25

export interface PageInfo {
  page: number // 1-based, clamped into range
  pages: number // total number of pages (at least 1)
  size: number
  total: number
  from: number // 1-based index of the first row shown (0 when empty)
  to: number // 1-based index of the last row shown
  start: number // slice start (0-based)
  end: number // slice end (exclusive)
}

export function pageInfo(total: number, page: number, size: number): PageInfo {
  const s = Math.max(1, Math.floor(size) || DEFAULT_PAGE_SIZE)
  const pages = Math.max(1, Math.ceil(total / s))
  const p = Math.min(Math.max(1, Math.floor(page) || 1), pages)
  const start = (p - 1) * s
  const end = Math.min(total, start + s)
  return { page: p, pages, size: s, total, from: total === 0 ? 0 : start + 1, to: end, start, end }
}

export function loadPageSize(): number {
  try {
    const v = Number(window.localStorage.getItem('pageSize'))
    return PAGE_SIZES.includes(v) ? v : DEFAULT_PAGE_SIZE
  } catch {
    return DEFAULT_PAGE_SIZE // storage can be blocked; the pager still works
  }
}

export function savePageSize(size: number): void {
  try {
    window.localStorage.setItem('pageSize', String(size))
  } catch { /* ignore */ }
}
