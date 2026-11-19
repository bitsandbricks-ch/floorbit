import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'
import { AreaDrift } from './AreaDrift'

describe('AreaDrift', () => {
  it('says where the switch is pinned and where the seat is, with the way to Switch areas', () => {
    renderWithApp(<AreaDrift drift={{ kind: 'pin', switch: 'sw-a-02', area: ['A 1'], row: 'A 2' }} />)
    expect(screen.getByText('sw-a-02 is pinned to A 1; this seat is in A 2.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Check it in Switch areas' })).toHaveAttribute('href', '/switch-areas')
  })

  it('shows nothing when the port fits the area', () => {
    renderWithApp(<AreaDrift drift={null} />)
    expect(screen.queryByRole('link', { name: 'Check it in Switch areas' })).not.toBeInTheDocument()
  })
})
