import { ActionIcon, Kbd, Stack, Tooltip } from '@mantine/core'
import { IconArmchair, IconBolt, IconBorderOuter, IconLetterT, IconLine, IconPlugConnected, IconPointer, IconServer2, IconStar } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { TOOL_KEYS, TOOLS, type Tool } from './tools'

const ICON: Record<Tool, typeof IconPointer> = {
  select: IconPointer, block: IconArmchair, text: IconLetterT, icon: IconStar, wall: IconLine, zone: IconBorderOuter,
  panel: IconServer2, cable: IconPlugConnected, board: IconBolt,
}

/** The Edit mode's tools down the left of the plan. */
export function ToolRail({ tool, onTool }: { tool: Tool; onTool: (t: Tool) => void }) {
  const { t } = useTranslation()
  return (
    <Stack gap={4} className="fb-edit-rail" role="toolbar" aria-orientation="vertical" aria-label={t('plan.edit.tools')}>
      {TOOLS.map((id) => {
        const Icon = ICON[id]
        const label = t(`plan.edit.tool.${id}`)
        return (
          <Tooltip key={id} position="right" label={<>{label} <Kbd size="xs">{TOOL_KEYS[id].toUpperCase()}</Kbd></>}>
            <ActionIcon size="lg" variant={tool === id ? 'filled' : 'subtle'} aria-label={label} aria-pressed={tool === id}
              aria-keyshortcuts={TOOL_KEYS[id].toUpperCase()} onClick={() => onTool(id)}>
              <Icon size={18} aria-hidden="true" />
            </ActionIcon>
          </Tooltip>
        )
      })}
    </Stack>
  )
}
