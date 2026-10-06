import { describe, expect, it } from 'vitest'
import { pageInfo } from './paging'

describe('pageInfo', () => {
  it('counts the total pages (101 lines, 25 per page = 5 pages)', () => {
    const p = pageInfo(101, 1, 25)
    expect(p.pages).toBe(5)
    expect([p.from, p.to, p.start, p.end]).toEqual([1, 25, 0, 25])
  })

  it('the last page holds the remainder', () => {
    const p = pageInfo(101, 5, 25)
    expect([p.from, p.to, p.start, p.end]).toEqual([101, 101, 100, 101])
  })

  it('an exact multiple has no empty trailing page', () => {
    expect(pageInfo(100, 1, 25).pages).toBe(4)
    expect(pageInfo(100, 4, 25).to).toBe(100)
  })

  it('clamps an out-of-range page (e.g. after changing the page size or refreshing a shorter order)', () => {
    expect(pageInfo(101, 99, 25).page).toBe(5)
    expect(pageInfo(101, 0, 25).page).toBe(1)
    expect(pageInfo(30, 5, 100).page).toBe(1)
  })

  it('handles an empty list', () => {
    const p = pageInfo(0, 1, 25)
    expect([p.pages, p.from, p.to, p.start, p.end]).toEqual([1, 0, 0, 0, 0])
  })
})
