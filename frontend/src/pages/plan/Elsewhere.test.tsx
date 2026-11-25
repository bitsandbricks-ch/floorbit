import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { Elsewhere } from './Elsewhere'

const halls = [
  { id: 'a', name: 'Hall A', problems: 2 },
  { id: 'b', name: 'Hall B', problems: 1 },
  { id: 'c', name: 'Hall C', problems: 3 },
]

describe('Problems in other halls (issue #874)', () => {
  it('names the one other hall and opens it', () => {
    const onHall = vi.fn()
    renderWithApp(<Elsewhere halls={halls.slice(0, 2)} current="a" onHall={onHall} />)
    const button = screen.getByRole('button', { name: '1 seat with problems in another hall' })
    expect(button).toHaveTextContent('+1 in Hall B')
    fireEvent.click(button)
    expect(onHall).toHaveBeenCalledWith('b')
  })

  it('sums several halls and opens the one with the most', () => {
    const onHall = vi.fn()
    renderWithApp(<Elsewhere halls={halls} current="b" onHall={onHall} />)
    const button = screen.getByRole('button', { name: '5 seats with problems in other halls' })
    expect(button).toHaveTextContent('+5 in other halls')
    fireEvent.click(button)
    expect(onHall).toHaveBeenCalledWith('c')
  })

  it('shows nothing when the other halls are fine', () => {
    renderWithApp(<Elsewhere halls={[{ id: 'a', name: 'A', problems: 4 }, { id: 'b', name: 'B', problems: 0 }]} current="a" onHall={() => {}} />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})
