import { ActionIcon, Kbd, Popover, SimpleGrid, Stack, Tooltip, UnstyledButton } from '@mantine/core'
import { useState } from 'react'
import { IconArmchair, IconBolt, IconEye, IconBorderOuter, IconChevronDown, IconGridDots, IconHandStop, IconRulerMeasure, IconLetterT, IconLine, IconPlugConnected, IconPointer, IconRouter, IconServer2, IconStar, IconWalk } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import './ToolRail.css'
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

/** Phones (Mike, 2026-11-26): no tall rail down the plan's edge. One button over the plan names the
 *  tool in hand and opens every tool as a grid; View goes back to the live plan. */
export function ToolPicker({ tool, onTool, onView }: { tool: Tool | null; onTool: (t: Tool) => void; onView: () => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const Now = tool ? ICON[tool] : IconEye
  const pick = (fn: () => void) => { setOpen(false); fn() }
  return (
    <Popover opened={open} onChange={setOpen} position="bottom-start" withinPortal shadow="md" width={300}>
      <Popover.Target>
        <UnstyledButton className="fb-tool-pick" aria-label={t('plan.edit.tools')} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <Now size={18} aria-hidden="true" />
          <span>{tool ? t(`plan.edit.tool.${tool}`) : t('plan.edit.tool.view')}</span>
          <IconChevronDown size={14} aria-hidden="true" />
        </UnstyledButton>
      </Popover.Target>
      <Popover.Dropdown p={8}>
        <SimpleGrid cols={4} spacing={6} role="toolbar" aria-label={t('plan.edit.tools')}>
          <UnstyledButton className="fb-tool-cell" aria-pressed={tool === null} onClick={() => pick(onView)}>
            <IconEye size={20} aria-hidden="true" /><span>{t('plan.edit.tool.view')}</span>
          </UnstyledButton>
          {TOOLS.map((id) => {
            const Icon = ICON[id]
            return (
              <UnstyledButton key={id} className="fb-tool-cell" aria-pressed={tool === id} onClick={() => pick(() => onTool(id))}>
                <Icon size={20} aria-hidden="true" /><span>{t(`plan.edit.tool.${id}`)}</span>
              </UnstyledButton>
            )
          })}
        </SimpleGrid>
      </Popover.Dropdown>
    </Popover>
  )
}
