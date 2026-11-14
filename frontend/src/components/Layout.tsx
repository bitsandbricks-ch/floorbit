import type { ReactNode } from 'react'
import { Anchor, Group } from '@mantine/core'
import { IconChevronLeft } from '@tabler/icons-react'
import { useEffect } from 'react'
import { Attribution } from './Attribution'
import { ThemeToggle, UserMenu } from './UserMenu'

/** Header with a way back, the page title, theme and user menu; the attribution at the end. */
export function Layout({ title, back, children }: { title: string; back: { href: string; label: string }; children: ReactNode }) {
  useEffect(() => {
    document.title = `${title} · Floorbit`
  }, [title])
  return (
    <>
      <header className="fb-header">
        {/* The floor plan and settings are still server pages: a full page load, not a route. */}
        <Anchor href={back.href} c="dimmed" size="sm" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <IconChevronLeft size={16} aria-hidden="true" />
          {back.label}
        </Anchor>
        <h1>{title}</h1>
        <Group gap={4} ml="auto" wrap="nowrap">
          <ThemeToggle />
          <UserMenu />
        </Group>
      </header>
      <main className="fb-main">{children}</main>
      <Attribution />
    </>
  )
}
