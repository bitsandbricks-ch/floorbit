/** The plan as a picture file (print sheet): the map's SVG with its styles written onto each
 *  element, so it looks the same outside the app, as SVG or rendered to PNG. */

// What the plan's CSS sets on SVG elements; copying only these keeps the file small.
const PROPS = ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-opacity', 'stroke-linecap', 'stroke-linejoin',
  'opacity', 'font-family', 'font-size', 'font-weight', 'text-anchor', 'dominant-baseline', 'paint-order', 'visibility', 'display']

/** A standalone copy of ``svg`` as it is in view: computed styles inlined, ``width`` pixels wide.
 *  Hidden parts and the editor's handles are left out. Returns the text and its pixel size. */
export function standaloneSvg(svg: SVGSVGElement, width: number): { text: string; width: number; height: number } {
  const vb = svg.viewBox.baseVal
  const box = { x: vb.x, y: vb.y, w: vb.width || 1, h: vb.height || 1 }
  const height = Math.round((width * box.h) / box.w)
  const copy = svg.cloneNode(true) as SVGSVGElement
  const from = [svg, ...svg.querySelectorAll('*')]
  const to = [copy, ...copy.querySelectorAll('*')]
  const drop: Element[] = []
  from.forEach((el, i) => {
    const out = to[i] as SVGElement
    const cs = getComputedStyle(el)
    // Editor-only drawing (handles, selection, rulers, padlocks) stays out of the picture.
    if (cs.display === 'none' || [...el.classList].some((c) => c.startsWith('fb-edit')) || el.hasAttribute('data-handle')) { drop.push(out); return }
    const style = PROPS.map((p) => [p, cs.getPropertyValue(p)] as const).filter(([, v]) => v).map(([p, v]) => `${p}:${v}`).join(';')
    if (style) out.setAttribute('style', style)
    out.removeAttribute('class')
    for (const a of ['tabindex', 'role', 'aria-label', 'aria-describedby']) out.removeAttribute(a)
  })
  drop.forEach((el) => el.remove())
  copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  copy.setAttribute('viewBox', `${box.x} ${box.y} ${box.w} ${box.h}`)
  copy.setAttribute('width', String(Math.round(width)))
  copy.setAttribute('height', String(height))
  return { text: new XMLSerializer().serializeToString(copy), width: Math.round(width), height }
}

/** Background images point at the server; a picture file needs them inside it. */
export async function inlineImages(svgText: string): Promise<string> {
  const doc = new DOMParser().parseFromString(svgText, 'image/svg+xml')
  for (const img of doc.querySelectorAll('image')) {
    const href = img.getAttribute('href')
    if (!href || href.startsWith('data:')) continue
    try {
      const blob = await (await fetch(href)).blob()
      img.setAttribute('href', await new Promise<string>((ok, no) => {
        const r = new FileReader(); r.onload = () => ok(String(r.result)); r.onerror = no; r.readAsDataURL(blob)
      }))
    } catch {
      img.remove()   // better a plan without its background than no file
    }
  }
  return new XMLSerializer().serializeToString(doc)
}

/** The SVG drawn onto a canvas of ``page`` colour (white for the print sheet), as a PNG. */
export async function svgToPng(svgText: string, width: number, height: number, page = '#fff'): Promise<Blob> {
  const url = URL.createObjectURL(new Blob([svgText], { type: 'image/svg+xml' }))
  try {
    const img = new Image()
    await new Promise<void>((ok, no) => { img.onload = () => ok(); img.onerror = () => no(new Error('render')); img.src = url })
    const canvas = document.createElement('canvas')
    canvas.width = width; canvas.height = height
    const g = canvas.getContext('2d')!
    g.fillStyle = page; g.fillRect(0, 0, width, height)
    g.drawImage(img, 0, 0, width, height)
    return await new Promise<Blob>((ok, no) => canvas.toBlob((b) => (b ? ok(b) : no(new Error('png'))), 'image/png'))
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** Hands ``blob`` to the browser as a download called ``name``. */
export function download(blob: Blob, name: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = name
  document.body.append(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

/** A file name from the hall's name: letters, digits and dashes only. */
export function fileName(hall: string, ext: string): string {
  const base = hall.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  return `floor-plan${base ? `-${base}` : ''}.${ext}`
}
