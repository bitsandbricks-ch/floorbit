import type { AnchorHTMLAttributes, Ref } from 'react'
import { Link } from 'react-router-dom'
import { inApp } from './inApp'

/** The link the shared components use (sidebar, breadcrumbs, side panels): a route inside the
 *  React app, a plain link for a page Flask draws or a big-screen view, so those load in full. */
export function AppLink({ to, ref, ...rest }: { to: string; ref?: Ref<HTMLAnchorElement> } & AnchorHTMLAttributes<HTMLAnchorElement>) {
  if (!inApp(to)) return <a ref={ref} href={to} {...rest} />
  return <Link ref={ref} to={to} {...rest} />
}
