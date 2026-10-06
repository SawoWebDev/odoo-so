export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : (detail as { message?: string })?.message ?? `HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

const HEADERS = { 'X-Requested-With': 'sticker-app' }

async function raise(r: Response): Promise<never> {
  let detail: unknown = r.statusText
  try {
    const j = await r.json()
    detail = j.detail ?? j
    if (Array.isArray(detail)) detail = detail.map((d: { msg?: string }) => d.msg).join('; ')
  } catch { /* not JSON */ }
  throw new ApiError(r.status, detail)
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init
  const headers: Record<string, string> = { ...HEADERS, ...(rest.headers as Record<string, string> | undefined) }
  if (json !== undefined) headers['Content-Type'] = 'application/json'
  const r = await fetch(`/api${path}`, {
    credentials: 'same-origin', ...rest, headers, body: json !== undefined ? JSON.stringify(json) : rest.body,
  })
  if (!r.ok) await raise(r)
  return (await r.json()) as T
}

export async function apiBlob(path: string, json: unknown): Promise<{ blob: Blob; headers: Headers }> {
  const r = await fetch(`/api${path}`, {
    method: 'POST', credentials: 'same-origin', headers: { ...HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify(json),
  })
  if (!r.ok) await raise(r)
  return { blob: await r.blob(), headers: r.headers }
}

export function form(data: Record<string, string | number | boolean | Blob | undefined | null>): FormData {
  const f = new FormData()
  for (const [k, v] of Object.entries(data)) if (v !== undefined && v !== null) f.append(k, v instanceof Blob ? v : String(v))
  return f
}

export function b64ToBlobUrl(b64: string, type = 'application/pdf'): string {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return URL.createObjectURL(new Blob([bytes], { type }))
}
