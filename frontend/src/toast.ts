export type ToastKind = 'success' | 'error'
export interface Toast { id: number; kind: ToastKind; message: string }

let items: Toast[] = []
let nextId = 1
const listeners = new Set<(items: Toast[]) => void>()

function emit() {
  for (const l of listeners) l(items)
}

export function subscribe(listener: (items: Toast[]) => void): () => void {
  listeners.add(listener)
  listener(items)
  return () => listeners.delete(listener)
}

export function dismissToast(id: number) {
  items = items.filter((t) => t.id !== id)
  emit()
}

function push(kind: ToastKind, message: string) {
  const id = nextId++
  items = [...items, { id, kind, message }]
  emit()
  setTimeout(() => dismissToast(id), 4000)
}

export const toast = {
  success: (message: string) => push('success', message),
  error: (message: string) => push('error', message),
}
