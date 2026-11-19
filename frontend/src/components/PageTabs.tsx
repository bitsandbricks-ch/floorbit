import type { ReactNode } from 'react'

export interface PageTab {
  id: string
  label: ReactNode
  /** A number after the label (items in the tab). */
  count?: number | null
  /** Something in the tab needs a look: a small bit after the label. */
  alert?: 'down' | 'warn' | null
  icon?: ReactNode
}

/** A page's tabs under its header, with counts: one row that scrolls sideways when there are
 *  more than fit, so a page can grow tabs (more agents, more halls) without wrapping. The page
 *  draws the panel for ``value`` itself. */
export function PageTabs({ tabs, value, onChange, label }: {
  tabs: PageTab[]; value: string; onChange: (id: string) => void; label: string
}) {
  const move = (from: number, step: number) => {
    const next = tabs[(from + step + tabs.length) % tabs.length]
    onChange(next.id)
    document.getElementById(`fb-tab-${next.id}`)?.focus()
  }
  return (
    <div className="fb-ptabs" role="tablist" aria-label={label}>
      {tabs.map((tab, i) => (
        <button
          key={tab.id} id={`fb-tab-${tab.id}`} type="button" role="tab" className="fb-ptab"
          aria-selected={tab.id === value} tabIndex={tab.id === value ? 0 : -1}
          onClick={() => onChange(tab.id)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowRight') { e.preventDefault(); move(i, 1) }
            if (e.key === 'ArrowLeft') { e.preventDefault(); move(i, -1) }
          }}
        >
          {tab.icon}
          <span>{tab.label}</span>
          {tab.count != null && <small className="fb-ptab-count">{tab.count}</small>}
          {tab.alert && <span className={`fb-bit is-${tab.alert}`} aria-hidden="true" />}
        </button>
      ))}
    </div>
  )
}
