// The panel a list or form sits in, now the shared Card (#1274). Pages still say Panel, so the
// switch didn't touch every page while other pull requests edit them.
import { Card } from '@bitsandbricks/ui'
import type { CSSProperties, ReactNode } from 'react'

/** The bordered panel a list, a form or a group of facts sits in: the shared Card as a section
 *  under the page's title (h2), named by its title. With a ``title``, a header row with the title,
 *  an optional line under it and ``actions`` at the end. */
export function Panel({ title, desc, actions, children, padding = 'md', style, className, id, 'aria-label': ariaLabel }: {
  title?: ReactNode; desc?: ReactNode; actions?: ReactNode; children?: ReactNode
  /** Was the title's id; the shared Card names the section by its heading itself. */
  titleId?: string
  /** 0 when the content brings its own (a table that runs to the edges). */
  padding?: 0 | 'md'; style?: CSSProperties; className?: string
  'aria-label'?: string; id?: string
}) {
  return (
    <Card title={title} desc={desc} actions={actions} heading={2} padded={padding !== 0} id={id} aria-label={ariaLabel}
      className={className} style={style}>
      {children}
    </Card>
  )
}
