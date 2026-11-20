import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { ErrorBanner, LoadingState } from './ui'

describe('loading and error states (#1017)', () => {
  it('loads as the shape of the content: page blocks, or text lines for a panel or pane', () => {
    const { container, unmount } = renderWithApp(<LoadingState />)
    expect(screen.getByRole('status', { name: 'Loading…' })).toHaveAttribute('aria-busy', 'true')
    expect(container.querySelectorAll('.mantine-Skeleton-root')).toHaveLength(3)
    unmount()
    const lines = renderWithApp(<LoadingState lines rows={2} />)
    expect(lines.container.querySelectorAll('.mantine-Skeleton-root')).toHaveLength(2)
  })

  it('says what failed and tries again', () => {
    const retry = vi.fn()
    renderWithApp(<ErrorBanner error={new Error('The server did not answer.')} onRetry={retry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('The server did not answer.')
    fireEvent.click(screen.getByRole('button', { name: /try again|retry/i }))
    expect(retry).toHaveBeenCalled()
  })
})
