import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useEffect, useRef } from 'react'

export interface TerminalHandle {
  write: (data: string) => void
  focus: () => void
}

/** xterm.js in a box: hands keystrokes to onData and its size to onResize. Kept apart from the
 *  page so tests can stand in a plain element for it (jsdom has no canvas). */
export function TerminalView({
  onReady,
  onData,
  onResize,
}: {
  onReady: (t: TerminalHandle) => void
  onData: (data: string) => void
  onResize: (cols: number, rows: number) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const handlers = useRef({ onReady, onData, onResize })
  useEffect(() => {
    handlers.current = { onReady, onData, onResize }
  })
  useEffect(() => {
    if (!box.current) return
    const term = new Terminal({
      cursorBlink: true,
      // A real font list: xterm measures glyphs on a canvas, which can't read CSS variables.
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', 'Liberation Mono', monospace",
      fontSize: 13,
      scrollback: 5000,
      theme: { background: '#0f1419', foreground: '#e6e6e6' },
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(box.current)
    const refit = () => {
      try {
        fit.fit()
      } catch {
        /* hidden or detached: try again on the next resize */
      }
    }
    refit()
    const data = term.onData((d) => handlers.current.onData(d))
    const size = term.onResize(({ cols, rows }) => handlers.current.onResize(cols, rows))
    const observer = new ResizeObserver(refit)
    observer.observe(box.current)
    handlers.current.onReady({ write: (d) => term.write(d), focus: () => term.focus() })
    handlers.current.onResize(term.cols, term.rows)
    term.focus()
    return () => {
      observer.disconnect()
      data.dispose()
      size.dispose()
      term.dispose()
    }
  }, [])
  return <div ref={box} className="fb-terminal" style={{ height: '100%', width: '100%' }} />
}
