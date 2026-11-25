import { type Section, rows } from './grid'
import { type Node, isPane } from './model'

/** A dashboard's grid as boxes, for the list. */
export function Thumbs({ sections }: { sections: Section[] }) {
  return (
    <div className="fb-thumb-grid">
      {sections.map((s, i) => (
        <div key={i} className="fb-thumb-section" style={{ flex: `${Math.max(1, rows(s.panels))} 1 0`, gridTemplateRows: `repeat(${Math.max(1, rows(s.panels))}, 1fr)` }}>
          {s.panels.map((p, j) => (
            <div key={j} style={{ gridColumn: `${p.x + 1} / span ${p.w}`, gridRow: `${p.y + 1} / span ${p.h}`, display: 'flex' }}><Thumb node={p.node} /></div>
          ))}
        </div>
      ))}
    </div>
  )
}

function Thumb({ node }: { node: Node }) {
  if (isPane(node)) return <div className={`fb-thumb-pane k-${node.pane.kind}`} />
  return (
    <div className={`fb-split fb-split-${node.split}`}>
      {node.children.map((c, i) => <div key={i} className="fb-split-part" style={{ flexBasis: `${node.sizes[i]}%` }}><Thumb node={c} /></div>)}
    </div>
  )
}
