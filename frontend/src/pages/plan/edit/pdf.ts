/** A PDF floor plan's first page as an image the hall can take as its background. pdf.js loads only
 *  when someone picks a PDF, so the editor stays as small as it was. */
const LONGEST = 3200          // pixels on the longest side: sharp when zoomed in, under the 5 MB limit
const MAX_BYTES = 5 * 1024 * 1024

export async function pdfToImage(file: File): Promise<string> {
  const [pdfjs, worker] = await Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url')])
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default
  const task = pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) })
  const doc = await task.promise
  try {
    const page = await doc.getPage(1)
    const base = page.getViewport({ scale: 1 })
    const viewport = page.getViewport({ scale: LONGEST / Math.max(base.width, base.height) })
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(viewport.width)
    canvas.height = Math.round(viewport.height)
    const g = canvas.getContext('2d')!
    // Plans are often drawn on nothing: white keeps lines readable on the dark theme.
    g.fillStyle = '#ffffff'
    g.fillRect(0, 0, canvas.width, canvas.height)
    await page.render({ canvas, canvasContext: g, viewport }).promise
    const png = canvas.toDataURL('image/png')
    return png.length * 0.75 <= MAX_BYTES ? png : canvas.toDataURL('image/jpeg', 0.85)
  } finally {
    void task.destroy()
  }
}
