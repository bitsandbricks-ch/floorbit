import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { ConfirmIcon } from './ConfirmButton'

describe('ConfirmIcon', () => {
  it('asks before it acts, and does nothing on cancel', async () => {
    const onConfirm = vi.fn()
    renderWithApp(<ConfirmIcon label="Delete Doors open" onConfirm={onConfirm}>x</ConfirmIcon>)
    fireEvent.click(screen.getByRole('button', { name: 'Delete Doors open' }))
    expect(await screen.findByText('Delete Doors open: are you sure?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onConfirm).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Delete Doors open' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, go ahead' }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })
})
