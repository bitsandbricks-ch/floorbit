import { Modal, Table } from '@mantine/core'
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'

describe('Providers', () => {
  it('names the close button of every dialog (issue #284)', async () => {
    renderWithApp(<Modal opened onClose={() => {}} title="Something">Body</Modal>)
    expect(await screen.findByRole('button', { name: 'Close' })).toBeInTheDocument()
  })

  it('keeps a name a dialog gives itself', async () => {
    renderWithApp(<Modal opened onClose={() => {}} title="Mute" closeButtonProps={{ 'aria-label': 'Cancel' }}>Body</Modal>)
    expect(await screen.findByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })

  it('lets the keyboard scroll a wide table (issue #286)', () => {
    const { container } = renderWithApp(
      <Table.ScrollContainer minWidth={800}><Table><Table.Tbody><Table.Tr><Table.Td>x</Table.Td></Table.Tr></Table.Tbody></Table></Table.ScrollContainer>)
    expect(container.querySelector('.mantine-ScrollArea-viewport')).toHaveAttribute('tabindex', '0')
  })
})
