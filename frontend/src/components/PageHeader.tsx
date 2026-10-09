import { NAV, type Tab } from '../nav'

export default function PageHeader({ tab }: { tab: Tab }) {
  const n = NAV.find((x) => x.id === tab)
  if (!n) return null
  return (
    <div className="page-header-bar">
      <header className="page-header">
        <span className="page-header-icon"><n.icon width={20} height={20} /></span>
        <div>
          <h1>{n.label}</h1>
          <p className="muted small">{n.description}</p>
        </div>
      </header>
    </div>
  )
}
