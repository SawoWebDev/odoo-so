export type ThemeName = 'light' | 'dark'

const KEY = 'theme'
// Same feel as the Helpdesk's reveal: a slow-in, slow-out circle over 750ms.
const REVEAL_MS = 750
const REVEAL_EASE = 'cubic-bezier(0.65, 0, 0.35, 1)'

/** The theme saved in this browser; each person's browser keeps its own. */
export function getTheme(): ThemeName {
  try { return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light' } catch { return 'light' }
}

export function setDocumentTheme(t: ThemeName) {
  document.documentElement.setAttribute('data-theme', t)
}

function saveTheme(t: ThemeName) {
  try { localStorage.setItem(KEY, t) } catch { /* private mode: the theme just isn't remembered */ }
}

type ViewTransitionDoc = Document & { startViewTransition?: (cb: () => void) => { ready: Promise<void> } }

/**
 * Switches theme with a circle growing out of `from` (the toggle's centre); falls back to an instant switch.
 * `onApply` runs inside the switch so UI that depends on the theme (the toggle's icon) is in the new snapshot too.
 */
export function toggleTheme(from: HTMLElement, onApply: (t: ThemeName) => void) {
  const next: ThemeName = getTheme() === 'dark' ? 'light' : 'dark'
  const apply = () => { setDocumentTheme(next); saveTheme(next); onApply(next) }
  const doc = document as ViewTransitionDoc
  if (!doc.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    apply()
    return
  }
  const box = from.getBoundingClientRect()
  const x = box.left + box.width / 2
  const y = box.top + box.height / 2
  const r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y))
  doc.startViewTransition(apply).ready.then(() => {
    document.documentElement.animate(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
      { duration: REVEAL_MS, easing: REVEAL_EASE, pseudoElement: '::view-transition-new(root)' },
    )
  })
}
