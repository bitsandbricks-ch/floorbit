import type { EventFrame, PlanDrawing } from '@/api/types'

/** Whether this browser can record a canvas to a video file. */
export function canRecord(): boolean {
  return typeof MediaRecorder !== 'undefined' && typeof HTMLCanvasElement !== 'undefined'
    && typeof HTMLCanvasElement.prototype.captureStream === 'function'
}

function cssVar(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

const W = 1280
const H = 720
const FPS = 8
export const MAX_VIDEO_FRAMES = 600   // 75 seconds of video, whatever the event's length

/** Every n-th frame so a long event still makes a short video. */
export function videoFrames(frames: EventFrame[]): EventFrame[] {
  const every = Math.max(1, Math.ceil(frames.length / MAX_VIDEO_FRAMES))
  return frames.filter((_, i) => i % every === 0 || i === frames.length - 1)
}

function draw(ctx: CanvasRenderingContext2D, drawing: PlanDrawing, f: EventFrame, caption: string, colors: Record<string, string>) {
  const [bx, by, bw, bh] = drawing.box.split(' ').map(Number)
  ctx.fillStyle = colors.bg
  ctx.fillRect(0, 0, W, H)
  const top = 70
  const scale = Math.min(W / bw, (H - top) / bh)
  const on = new Set(f.seats)
  const rings = new Set(f.incidents)
  ctx.save()
  ctx.translate((W - bw * scale) / 2, top + (H - top - bh * scale) / 2)
  ctx.scale(scale, scale)
  ctx.translate(-bx, -by)
  for (const b of drawing.shapes) {
    ctx.save()
    ctx.translate(b.cx, b.cy)
    ctx.rotate((b.rotation * Math.PI) / 180)
    for (const c of b.cells) {
      ctx.fillStyle = on.has(c.seat) ? colors.up : colors.cell
      ctx.fillRect(c.x + 1, c.y + 1, drawing.cell - 2, drawing.cell - 2)
      if (rings.has(c.seat)) {
        ctx.strokeStyle = colors.down
        ctx.lineWidth = 4
        ctx.beginPath()
        ctx.arc(c.x + drawing.cell / 2, c.y + drawing.cell / 2, drawing.cell * 0.9, 0, Math.PI * 2)
        ctx.stroke()
      }
    }
    ctx.restore()
    if (b.name) {
      ctx.fillStyle = colors.muted
      ctx.font = '700 34px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(b.name, b.cx, b.cy - Math.max(b.w, b.h) / 2 - 18)
    }
  }
  ctx.restore()
  ctx.fillStyle = colors.fg
  ctx.font = '700 32px sans-serif'
  ctx.textAlign = 'left'
  ctx.fillText(caption, 32, 48)
}

/**
 * Plays the frames onto a canvas and records it with the browser's MediaRecorder: a WebM file,
 * with no extra library. ``caption`` writes the line at the top of each frame.
 */
export async function recordVideo(drawing: PlanDrawing, frames: EventFrame[], caption: (f: EventFrame) => string,
  onProgress: (done: number) => void): Promise<Blob> {
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('No canvas')
  const colors = {
    bg: cssVar('--color-raised', '#111'), cell: cssVar('--color-surface', '#222'), up: cssVar('--color-up', '#3c3'),
    down: cssVar('--color-down', '#e33'), muted: cssVar('--color-muted', '#888'), fg: cssVar('--color-fg', '#fff'),
  }
  const list = videoFrames(frames)
  draw(ctx, drawing, list[0], caption(list[0]), colors)
  const stream = canvas.captureStream(FPS)
  const type = ['video/webm;codecs=vp9', 'video/webm'].find((m) => MediaRecorder.isTypeSupported(m)) ?? ''
  const rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined)
  const chunks: Blob[] = []
  rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
  const stopped = new Promise<void>((resolve) => { rec.onstop = () => resolve() })
  rec.start()
  for (let i = 0; i < list.length; i++) {
    draw(ctx, drawing, list[i], caption(list[i]), colors)
    onProgress((i + 1) / list.length)
    await new Promise((r) => window.setTimeout(r, 1000 / FPS))
  }
  rec.stop()
  await stopped
  return new Blob(chunks, { type: 'video/webm' })
}
