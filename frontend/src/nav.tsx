import { ActivityIcon, CameraIcon, FolderIcon, HistoryIcon, InboxIcon, SettingsIcon, UsersIcon } from './components/icons'

export type Tab = 'trace' | 'labels' | 'requests' | 'history' | 'users' | 'settings' | 'activity'

export interface NavItem {
  id: Tab
  label: string
  description: string
  icon: typeof CameraIcon
  adminOnly?: boolean
}

export const NAV: NavItem[] = [
  { id: 'trace', label: 'Trace & print', description: 'Find a sales order by number or item, then print its labels.', icon: CameraIcon },
  { id: 'labels', label: 'Label files', description: 'Add the folders that hold label files and search what’s saved.', icon: FolderIcon },
  { id: 'requests', label: 'Requests', description: 'Review and resolve label requests sent in from the floor.', icon: InboxIcon },
  { id: 'history', label: 'Print history', description: 'See everything that’s been printed, and reprint a past job.', icon: HistoryIcon },
  { id: 'settings', label: 'Settings', description: 'Configure email notifications and who receives them.', icon: SettingsIcon, adminOnly: true },
  { id: 'users', label: 'Roles', description: 'Manage user accounts and their access roles.', icon: UsersIcon, adminOnly: true },
  { id: 'activity', label: 'Activity log', description: 'Who did what, and when: sign-ins, searches, prints and changes.', icon: ActivityIcon, adminOnly: true },
]

const PATH_TO_TAB: Record<string, Tab> = { '/': 'trace' }
for (const n of NAV) if (n.id !== 'trace') PATH_TO_TAB[`/${n.id}`] = n.id

export function tabForPath(path: string): Tab {
  return PATH_TO_TAB[path] ?? 'trace'
}

export function pathForTab(tab: Tab): string {
  return tab === 'trace' ? '/' : `/${tab}`
}
