import { Anchor, Code, List, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'

/* A small Markdown subset for runbooks: headings, numbered and bullet lists, paragraphs, **bold**,
   `code` and [links](https://...). It builds React elements, never HTML, so nothing typed can run. */

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g

function inline(text: string): ReactNode[] {
  return text.split(INLINE).filter(Boolean).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) return <Code key={i}>{part.slice(1, -1)}</Code>
    const link = part.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/)
    if (link) {
      const safe = /^(https?:\/\/|\/(?!\/))/.test(link[2])
      return safe ? <Anchor key={i} href={link[2]} target={link[2].startsWith('/') ? undefined : '_blank'} rel="noreferrer">{link[1]}</Anchor> : link[1]
    }
    return part
  })
}

type Block = { kind: 'h'; level: number; text: string } | { kind: 'ol' | 'ul'; items: string[] } | { kind: 'p'; text: string }

function blocks(source: string): Block[] {
  const out: Block[] = []
  for (const raw of source.replace(/\r\n/g, '\n').split('\n')) {
    const line = raw.trim()
    const last = out[out.length - 1]
    const heading = line.match(/^(#{1,3})\s+(.*)$/)
    const ol = line.match(/^\d+[.)]\s+(.*)$/)
    const ul = line.match(/^[-*]\s+(.*)$/)
    if (!line) out.push({ kind: 'p', text: '' })
    else if (heading) out.push({ kind: 'h', level: heading[1].length, text: heading[2] })
    else if (ol || ul) {
      const kind = ol ? 'ol' : 'ul'
      const text = (ol ?? ul)![1]
      if (last && last.kind === kind) last.items.push(text)
      else out.push({ kind, items: [text] })
    } else if (last && last.kind === 'p' && last.text) last.text += ` ${line}`
    else if (last && (last.kind === 'ol' || last.kind === 'ul') && raw.startsWith(' ')) last.items[last.items.length - 1] += ` ${line}`
    else out.push({ kind: 'p', text: line })
  }
  return out.filter((b) => b.kind !== 'p' || b.text)
}

export function Markdown({ source }: { source: string }) {
  return (
    <div className="fb-markdown">
      {blocks(source).map((b, i) => {
        if (b.kind === 'h') return <Title key={i} order={Math.min(6, b.level + 2) as 3 | 4 | 5} mt="xs" mb={4}>{inline(b.text)}</Title>
        if (b.kind === 'p') return <Text key={i} size="sm" mb="xs">{inline(b.text)}</Text>
        return (
          <List key={i} type={b.kind === 'ol' ? 'ordered' : 'unordered'} size="sm" spacing={4} mb="xs" withPadding>
            {b.items.map((item, n) => <List.Item key={n}>{inline(item)}</List.Item>)}
          </List>
        )
      })}
    </div>
  )
}
