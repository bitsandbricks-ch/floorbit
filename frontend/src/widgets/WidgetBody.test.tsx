import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Widget } from '@/api/types'
import { renderWithApp } from '@/test/render'
import { sparkPoints } from './spark'
import { WidgetBody } from './WidgetBody'

const base = { id: 'w', label: 'W', size: 'small', refresh: 60, sub: '', link: '' } as const

describe('WidgetBody', () => {
  it('draws a stat with its unit and tone', () => {
    renderWithApp(<WidgetBody widget={{ ...base, type: 'stat', value: 42, unit: 'Mbit/s', tone: 'warn' }} />)
    expect(screen.getByText('42')).toHaveClass('fb-tone-warn')
    expect(screen.getByText('Mbit/s')).toBeInTheDocument()
  })

  it('draws status items with a labelled dot', () => {
    renderWithApp(
      <WidgetBody widget={{ ...base, type: 'status', items: [{ label: 'DNS', state: 'down', detail: 'timeout' }] }} />,
    )
    expect(screen.getByRole('img', { name: 'down' })).toHaveClass('fb-dot', 'down')
    expect(screen.getByText('timeout')).toBeInTheDocument()
  })

  it('draws a table', () => {
    renderWithApp(
      <WidgetBody
        widget={{ ...base, type: 'table', columns: [{ key: 'name', label: 'Name' }], rows: [{ name: 'sw-a-01' }] }}
      />,
    )
    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'sw-a-01' })).toBeInTheDocument()
  })

  it('shows plugin text as text, never as HTML', () => {
    const { container } = renderWithApp(
      <WidgetBody widget={{ ...base, type: 'list', items: [{ label: '<img src=x onerror=alert(1)>', value: '1', tone: '' }] }} />,
    )
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('says so when it does not know the type', () => {
    renderWithApp(<WidgetBody widget={{ ...base, type: 'pie' } as unknown as Widget} />)
    expect(screen.getByText("This tile can't be drawn.")).toBeInTheDocument()
  })
})

describe('sparkPoints', () => {
  it('scales points into the 100 x 30 box', () => {
    expect(sparkPoints([0, 10], 0, 10)).toBe('0,29 100,1')
  })
  it('needs two points', () => {
    expect(sparkPoints([5])).toBe('')
  })
})
