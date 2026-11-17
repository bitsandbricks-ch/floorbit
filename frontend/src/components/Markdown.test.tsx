import { render, screen } from '@testing-library/react'
import { MantineProvider } from '@mantine/core'
import { describe, expect, it } from 'vitest'
import { Markdown } from './Markdown'

const show = (source: string) => render(<MantineProvider><Markdown source={source} /></MantineProvider>)

describe('Markdown', () => {
  it('renders lists, bold, code and safe links only', () => {
    const { container } = show('## Steps\n1. Check the **cable**\n2. Run `show int`\n\n- [docs](https://example.com)\n- [bad](javascript:alert(1))\n\n<b>raw</b>')
    expect(screen.getByRole('heading', { name: 'Steps' })).toBeInTheDocument()
    expect(container.querySelectorAll('ol li')).toHaveLength(2)
    expect(container.querySelector('strong')?.textContent).toBe('cable')
    expect(container.querySelector('code')?.textContent).toBe('show int')
    expect(screen.getByRole('link', { name: 'docs' })).toHaveAttribute('href', 'https://example.com')
    expect(screen.queryByRole('link', { name: 'bad' })).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(screen.getByText('<b>raw</b>')).toBeInTheDocument()
  })

  it('joins lines into a paragraph, or keeps each line with breaks', () => {
    expect(show('one\ntwo').container.querySelectorAll('p')).toHaveLength(1)
    const { container } = render(<MantineProvider><Markdown source={'one\ntwo'} breaks /></MantineProvider>)
    expect(container.querySelectorAll('p')).toHaveLength(2)
  })
})
