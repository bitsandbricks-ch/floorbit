import { fireEvent, render, screen } from '@testing-library/react'
import { MantineProvider } from '@mantine/core'
import { describe, expect, it } from 'vitest'
import '@/i18n'
import { useMoreLines } from './MoreLines'

function Lines({ lines }: { lines: string[] }) {
  const { limit, more } = useMoreLines(lines.length, 3)
  return <MantineProvider><pre>{lines.slice(0, limit).join('\n')}</pre>{more}</MantineProvider>
}

describe('useMoreLines', () => {
  it('shows the first lines, then all of them in place on a click', () => {
    render(<Lines lines={['a', 'b', 'c', 'd', 'e']} />)
    expect(screen.queryByText(/^e$/m)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all 5 lines (2 more)' }))
    expect(screen.getByText(/e/)).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('has no button when everything fits', () => {
    render(<Lines lines={['a', 'b']} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
