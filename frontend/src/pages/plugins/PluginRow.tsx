import { Alert, Anchor, Text, Title } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PluginInfo } from '@/api/types'
import { pluginName } from '@/lib/pluginName'
import { PluginCard as Card } from './Card'
import { PluginIcon } from './icon'
import { Meta, OnOff, StateBadge } from './parts'
import { describe, useToggle } from './toggle'
import '../Plugins.css'

type Result = { ok: boolean; text: string } | null


/** One card of the list, the same slots on each (#1435): name and state at the top, one line on
 *  what it does, then where it comes from and its switch at the foot. */
export function PluginRow({ plugin }: { plugin: PluginInfo }) {
  const { t } = useTranslation()
  const [result, setResult] = useState<Result>(null)
  const toggle = useToggle(plugin, (ok, text) => setResult({ ok, text }))
  const href = `/settings/plugins/${encodeURIComponent(plugin.id)}`
  const about = plugin.description ? describe(plugin, t) : ''
  return (
    <Card id={`pl-${plugin.id}`} data-plugin={plugin.id}
      head={<><PluginIcon name={plugin.icon} />
        <Title order={2} fz="md" className="fb-plugin-card-name"><Anchor href={href} inherit>{pluginName(t, plugin.id, plugin.name)}</Anchor></Title></>}
      badge={<StateBadge plugin={plugin} />}
      about={about}
      foot={<><Meta plugin={plugin} /><OnOff plugin={plugin} toggle={toggle} bare /></>}>
      {plugin.error && <Alert color="down" role="alert" py="xs">✕ {plugin.error}</Alert>}
      {result && (
        <Text size="sm" role="status" className={result.ok ? 'fb-tone-ok' : 'fb-tone-err'}>
          {`${result.ok ? '✓' : '✕'} ${result.text}`}
        </Text>
      )}
    </Card>
  )
}

