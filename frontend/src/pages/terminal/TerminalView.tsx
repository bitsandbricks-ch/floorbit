import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useEffect, useRef } from 'react'

const FONT = "'Geist Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace"
/** Dark in both themes, like any console: the brand's page black, Bit Green cursor, Trace Cyan
 *  selection (static/css/brand/tokens.css). xterm draws on a canvas, so the values are spelled out. */
const THEME = {
  background: '#0b0b0f', foreground: '#e7e7ea', cursor: '#2ee59d', cursorAccent: '#0b0b0f',
  selectionBackground: 'rgba(34, 211, 238, 0.3)',
  black: '#1f1f28', brightBlack: '#71717a', red: '#f87171', brightRed: '#fca5a5', green: '#2ee59d', brightGreen: '#6ff0bd',
  yellow: '#fbbf24', brightYellow: '#fcd34d', blue: '#60a5fa', brightBlue: '#93c5fd', magenta: '#c084fc',
  brightMagenta: '#d8b4fe', cyan: '#22d3ee', brightCyan: '#67e8f9', white: '#d4d4d8', brightWhite: '#f4f4f5',
}

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
      fontFamily: FONT,
      fontSize: 13,
      lineHeight: 1.15,
      scrollback: 5000,
      theme: THEME,
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
    // Geist Mono may still be loading: measure again once it's there, or the cells come out too wide.
    void document.fonts?.load("13px 'Geist Mono'").then(() => {
      term.options.fontFamily = FONT
      refit()
    }).catch(() => undefined)
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
