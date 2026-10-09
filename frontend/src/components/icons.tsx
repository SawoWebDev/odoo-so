import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

const base = (props: IconProps): IconProps => ({
  width: 18, height: 18, viewBox: '0 0 24 24', fill: 'currentColor', stroke: 'none', ...props,
})

export function PrinterIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path fillRule="evenodd" clipRule="evenodd" d="M6 2.5h12a1 1 0 0 1 1 1V8h.5A2.5 2.5 0 0 1 22 10.5v5a2.5 2.5 0 0 1-2.5 2.5H19v2.5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V18h-.5A2.5 2.5 0 0 1 2 15.5v-5A2.5 2.5 0 0 1 4.5 8H5V3.5a1 1 0 0 1 1-1Zm1 2v3.5h10V4.5H7Zm0 10.5v4.5h10V15H7Zm9.5-3a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z" />
    </svg>
  )
}

export function FolderIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.17a1.5 1.5 0 0 1 1.06.44L11.5 7.2H19.5A1.5 1.5 0 0 1 21 8.7v8.8A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z" />
    </svg>
  )
}

export function InboxIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path fillRule="evenodd" clipRule="evenodd" d="M5.26 5a1 1 0 0 0-.97.76L2.5 12v6A2.5 2.5 0 0 0 5 20.5h14a2.5 2.5 0 0 0 2.5-2.5v-6l-1.79-6.24A1 1 0 0 0 18.74 5zM4.75 12l1.42-5h11.66l1.42 5H15.3l-1.1 2.2a1 1 0 0 1-.9.55h-2.6a1 1 0 0 1-.9-.55L8.7 12z" />
    </svg>
  )
}

export function HistoryIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path fillRule="evenodd" clipRule="evenodd" d="M12 3a8 8 0 1 1-7.75 10h2.1A6 6 0 1 0 6 8.5H8v2H3v-5h2v1.78A7.98 7.98 0 0 1 12 3Zm.75 4.25v4.44l3.1 1.8-.75 1.3-3.85-2.24V7.25z" />
    </svg>
  )
}

export function SettingsIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 6.75A1.25 1.25 0 0 1 5.25 5.5h13.5a1.25 1.25 0 1 1 0 2.5H5.25A1.25 1.25 0 0 1 4 6.75Z" />
      <path d="M4 17.25A1.25 1.25 0 0 1 5.25 16h13.5a1.25 1.25 0 1 1 0 2.5H5.25A1.25 1.25 0 0 1 4 17.25Z" />
      <path d="M4 12a1.25 1.25 0 0 1 1.25-1.25h13.5a1.25 1.25 0 1 1 0 2.5H5.25A1.25 1.25 0 0 1 4 12Z" />
      <circle cx="9" cy="6.75" r="2.25" />
      <circle cx="16" cy="17.25" r="2.25" />
      <circle cx="12.5" cy="12" r="2.25" />
    </svg>
  )
}

export function UsersIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="9" cy="7.6" r="3.4" />
      <path d="M2.8 19.4c.5-3.7 3.1-6 6.2-6s5.7 2.3 6.2 6a.9.9 0 0 1-.9 1H3.7a.9.9 0 0 1-.9-1Z" />
      <circle cx="17.3" cy="8.2" r="2.5" />
      <path d="M15.4 13.6c2.7.2 4.9 2.2 5.5 5.5a.85.85 0 0 1-.84 1H17" />
    </svg>
  )
}

/** Font Awesome 6 "right-from-bracket" (as in the Helpdesk), mirrored so the arrow points back toward the name. */
export function LogOutIcon(props: IconProps) {
  return (
    <svg {...base({ width: 16, height: 16, ...props })} viewBox="0 0 512 512" style={{ transform: 'scaleX(-1)', ...props.style }}>
      <path d="M377.9 105.9 500.7 228.7c7.2 7.2 11.3 17.1 11.3 27.3s-4.1 20.1-11.3 27.3L377.9 406.1c-6.4 6.4-15 9.9-24 9.9-18.7 0-33.9-15.2-33.9-33.9V320H192c-17.7 0-32-14.3-32-32v-64c0-17.7 14.3-32 32-32h128v-62.1c0-18.7 15.2-33.9 33.9-33.9 9 0 17.6 3.6 24 9.9ZM160 96H96c-17.7 0-32 14.3-32 32v256c0 17.7 14.3 32 32 32h64c17.7 0 32 14.3 32 32s-14.3 32-32 32H96c-53 0-96-43-96-96V128c0-53 43-96 96-96h64c17.7 0 32 14.3 32 32s-14.3 32-32 32Z" />
    </svg>
  )
}

/* Sun and moon as drawn by the Helpdesk's ThemeToggle */
export function SunIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="12" r="4.6" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
        <rect key={deg} x="11" y="1.5" width="2" height="4" rx="1" transform={`rotate(${deg} 12 12)`} />
      ))}
    </svg>
  )
}

export function MoonIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
    </svg>
  )
}

export function ChevronLeftIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M14.7 4.3a1 1 0 0 1 0 1.4L8.4 12l6.3 6.3a1 1 0 1 1-1.4 1.4l-7-7a1 1 0 0 1 0-1.4l7-7a1 1 0 0 1 1.4 0Z" />
    </svg>
  )
}

export function CameraIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path fillRule="evenodd" clipRule="evenodd" d="M9.17 4.5a1.5 1.5 0 0 0-1.25.68L6.9 6.5H5.5A2.5 2.5 0 0 0 3 9v8a2.5 2.5 0 0 0 2.5 2.5h13A2.5 2.5 0 0 0 21 17V9a2.5 2.5 0 0 0-2.5-2.5h-1.4l-1.02-1.32a1.5 1.5 0 0 0-1.25-.68ZM12 9.5a4 4 0 1 1 0 8 4 4 0 0 1 0-8Zm0 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z" />
    </svg>
  )
}

export function EyeIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path fillRule="evenodd" clipRule="evenodd" d="M12 5c-5.2 0-9.4 4-10.9 6.6a1.4 1.4 0 0 0 0 1.3C2.6 15.4 6.8 19.4 12 19.4s9.4-4 10.9-6.5a1.4 1.4 0 0 0 0-1.3C21.4 9 17.2 5 12 5Zm0 11.8a4.8 4.8 0 1 1 0-9.6 4.8 4.8 0 0 1 0 9.6Zm0-2.3a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" />
    </svg>
  )
}

export function ExpandIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 9V4h5v2H6v3H4Zm11-5h5v5h-2V6h-3V4ZM4 15h2v3h3v2H4v-5Zm13 3v-3h2v5h-5v-2h3Z" />
    </svg>
  )
}

export function XIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6.4 4.98 4.98 6.4 10.59 12l-5.61 5.6 1.42 1.42L12 13.41l5.6 5.61 1.42-1.42L13.41 12l5.61-5.6-1.42-1.42L12 10.59z" />
    </svg>
  )
}

export function FlagIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M5.5 2.5a1 1 0 0 1 1 1V21a1 1 0 1 1-2 0V3.5a1 1 0 0 1 1-1Z" />
      <path d="M7 3.8c2.1-1.1 4.3-1.1 6.3.1 1.9 1.2 3.9 1.2 5.8-.1a.85.85 0 0 1 1.34.7v8.3a.85.85 0 0 1-.37.7c-2.2 1.5-4.5 1.5-6.7.1-1.9-1.2-3.9-1.2-5.84 0a.6.6 0 0 1-.93-.5V3.8Z" />
    </svg>
  )
}

export function ActivityIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path fillRule="evenodd" clipRule="evenodd" d="M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm1.5 4a1 1 0 1 0 0 2 1 1 0 0 0 0-2Zm3 .25v1.5H17v-1.5zM7.5 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2Zm3 .25v1.5H17v-1.5zM7.5 15a1 1 0 1 0 0 2 1 1 0 0 0 0-2Zm3 .25v1.5H15v-1.5z" />
    </svg>
  )
}

export function PencilIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M15.6 3.6a2 2 0 0 1 2.83 0l1.97 1.97a2 2 0 0 1 0 2.83L9.5 19.3a1 1 0 0 1-.45.26l-4.8 1.3a.8.8 0 0 1-.98-.98l1.3-4.8a1 1 0 0 1 .26-.45zM14.2 7.8 6.8 15.2l-.75 2.75 2.75-.75 7.4-7.4z" />
    </svg>
  )
}

export function TrashIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path fillRule="evenodd" clipRule="evenodd" d="M9.5 3h5a1 1 0 0 1 1 1v1H20v2H4V5h4.5V4a1 1 0 0 1 1-1ZM5.5 8.5h13l-.8 11.1A1.5 1.5 0 0 1 16.2 21H7.8a1.5 1.5 0 0 1-1.5-1.4zM9.25 11v7h1.5v-7zm4 0v7h1.5v-7z" />
    </svg>
  )
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M20.7 6.3a1 1 0 0 1 0 1.4l-10.5 10.5a1 1 0 0 1-1.4 0l-5.5-5.5a1 1 0 1 1 1.4-1.4l4.8 4.79 9.8-9.8a1 1 0 0 1 1.4 0Z" />
    </svg>
  )
}
