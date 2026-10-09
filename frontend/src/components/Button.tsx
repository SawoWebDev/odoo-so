import type { ButtonHTMLAttributes } from 'react'

type Variant = 'default' | 'primary' | 'danger' | 'link' | 'icon' | 'nav'

export default function Button(
  { variant = 'default', className = '', active = false, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; active?: boolean },
) {
  const cls = [
    variant !== 'default' && variant !== 'nav' ? variant : '',
    variant === 'nav' && active ? 'on' : '',
    className,
  ].filter(Boolean).join(' ')
  // No default `type`: inside a <form>, a bare <button> submits — the same as plain HTML, so forms keep working.
  return <button className={cls || undefined} {...rest} />
}
