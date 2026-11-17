import { describe, expect, it } from 'vitest'
import { fileName, standaloneSvg } from './exportImage'

describe('saving the plan as a picture', () => {
  it('keeps the view, inlines styles and drops app-only parts', () => {
    document.body.innerHTML = `<style>.seat{fill:rgb(1, 2, 3)} .gone{display:none}</style>
      <svg viewBox="10 20 400 200" class="fb-plan" role="application" tabindex="0">
        <rect class="seat" width="5" height="5"/><g class="gone"><rect/></g><g class="fb-edit-handles"><rect/></g>
      </svg>`
    const out = standaloneSvg(document.querySelector('svg')!, 800)
    expect(out).toMatchObject({ width: 800, height: 400 })
    expect(out.text).toContain('viewBox="10 20 400 200"')
    expect(out.text).toContain('xmlns="http://www.w3.org/2000/svg"')
    expect(out.text).toContain('fill:rgb(1, 2, 3)')
    expect(out.text).not.toContain('class=')
    expect(out.text).not.toContain('role=')
    expect(out.text.match(/<rect/g)).toHaveLength(1)
  })
  it('names the file after the hall', () => {
    expect(fileName('Halle Süd 2', 'png')).toBe('floor-plan-halle-sud-2.png')
    expect(fileName('', 'svg')).toBe('floor-plan.svg')
  })
})
