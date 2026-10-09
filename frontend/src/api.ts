import { toast } from './toast'

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

const ACTION_LABEL: Record<string, string> = { POST: 'Sent', PUT: 'Saved', PATCH: 'Saved', DELETE: 'Deleted' }

async function raise(r: Response): Promise<never> {
  let detail: unknown = r.statusText
  try {
    const j = await r.json()
    detail = j.detail ?? j
    if (Array.isArray(detail)) detail = detail.map((d: { msg?: string }) => d.msg).join('; ')
  } catch { /* not JSON */ }
  const err = new ApiError(r.status, detail)
  toast.error(err.message)
  throw err
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init
  const headers: Record<string, string> = { ...HEADERS, ...(rest.headers as Record<string, string> | undefined) }
  if (json !== undefined) headers['Content-Type'] = 'application/json'
  const method = (rest.method ?? 'GET').toUpperCase()
  const r = await fetch(`/api${path}`, {
    credentials: 'same-origin', ...rest, headers, body: json !== undefined ? JSON.stringify(json) : rest.body,
  })
  if (!r.ok) await raise(r)
  const label = ACTION_LABEL[method]
  if (label) toast.success(label)
  return (await r.json()) as T
}

/** `done` is the success toast; null for read-only calls such as a preview, which change nothing. Errors always toast. */
export async function apiBlob(path: string, json: unknown, done: string | null): Promise<{ blob: Blob; headers: Headers }> {
  const r = await fetch(`/api${path}`, {
    method: 'POST', credentials: 'same-origin', headers: { ...HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify(json),
  })
  if (!r.ok) await raise(r)
  if (done) toast.success(done)
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
