import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SyslogLine } from '@/api/types'
import { renderWithApp } from '@/test/render'
import { Message } from './Message'

const line = (program: string, message: string): SyslogLine => ({
  id: 1, ts: 0, facility: 16, severity: 'info', host: null, program, message, sender: '192.0.2.1', device: 'fw-01', port: null, seat: null,
})

describe('a log message (issue #1429)', () => {
  it('reads a filterlog line, with the whole line on demand', () => {
    const raw = '5,,,1000000103,igb1,match,block,in,4,0x0,,64,1,0,none,17,udp,76,203.0.113.9,198.51.100.1,123,123,56'
    renderWithApp(<Message line={line('filterlog', raw)} />)
    expect(screen.getByText('block in · igb1 · UDP 203.0.113.9:123 → 198.51.100.1:123')).toBeInTheDocument()
    expect(screen.queryByText(raw)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Whole line' }))
    expect(screen.getByText(raw)).toBeInTheDocument()
  })

  it('shows any other line as it came', () => {
    renderWithApp(<Message line={line('dhcpd', 'DHCPACK on 192.0.2.40')} />)
    expect(screen.getByText('DHCPACK on 192.0.2.40')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
