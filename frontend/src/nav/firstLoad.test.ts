import { describe, expect, it } from 'vitest'
import appLink from './AppLink.tsx?raw'
import leaveGuard from '@/components/LeaveGuard.tsx?raw'
import publicPage from '@/components/PublicPage.tsx?raw'
import login from '@/pages/Login.tsx?raw'

// These load on every page, the public ones too (#1293): the sidebar's rows and icons, and
// Mantine's Modal, wait until a page needs them.
describe('what every page loads', () => {
  it('reads the brand and app links without the sidebar sections', () => {
    for (const source of [appLink, publicPage, login]) {
      expect(source).not.toMatch(/from '(\.\/|@\/nav\/)(sections|boot)'/)
    }
  })

  it('loads the leave dialog only when it is needed', () => {
    expect(leaveGuard).not.toMatch(/from '@mantine\/core'/)
    expect(leaveGuard).toContain("import('./LeaveDialog')")
  })
})
