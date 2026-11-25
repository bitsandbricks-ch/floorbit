import { ActionIcon, Kbd, Stack, Tooltip } from '@mantine/core'
import { IconArmchair, IconBolt, IconEye, IconBorderOuter, IconGridDots, IconHandStop, IconRulerMeasure, IconLetterT, IconLine, IconPlugConnected, IconPointer, IconRouter, IconServer2, IconStar, IconWalk } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { TOOL_KEYS, TOOLS, type Tool } from './tools'

const ICON: Record<Tool, typeof IconPointer> = {
  select: IconPointer, hand: IconHandStop, measure: IconRulerMeasure, block: IconArmchair, switch: IconRouter, text: IconLetterT, icon: IconStar, wall: IconLine, walkway: IconWalk, zone: IconBorderOuter, fill: IconGridDots,
  panel: IconServer2, cable: IconPlugConnected, board: IconBolt,
}

/** The plan's tools down the left, for crew who may change it. View (no tool) is the live plan,
 *  where a click opens a seat's details; any other tool takes up the editor. */
export function ToolRail({ tool, onTool, onView }: { tool: Tool | null; onTool: (t: Tool) => void; onView: () => void }) {
  const { t } = useTranslation()
  return (
    <Stack gap={4} className="fb-edit-rail" role="toolbar" aria-orientation="vertical" aria-label={t('plan.edit.tools')}>
      <Tooltip position="right" label={t('plan.edit.tool.viewHint')}>
        <ActionIcon size="lg" variant={tool === null ? 'filled' : 'subtle'} aria-label={t('plan.edit.tool.view')} aria-pressed={tool === null} onClick={onView}>
          <IconEye size={18} aria-hidden="true" />
        </ActionIcon>
      </Tooltip>
      <div className="fb-edit-rail-sep" role="separator" />
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
