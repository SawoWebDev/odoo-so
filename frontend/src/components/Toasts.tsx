import { useEffect, useState } from 'react'
import { dismissToast, subscribe, type Toast } from '../toast'

export default function Toasts() {
  const [items, setItems] = useState<Toast[]>([])
  useEffect(() => subscribe(setItems), [])
  if (!items.length) return null
  return (
    <div className="toasts">
      {items.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`} role="status" onClick={() => dismissToast(t.id)}>
          {t.message}
        </div>
      ))}
    </div>
  )
}
