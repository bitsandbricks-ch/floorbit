import { Anchor, Badge, Group, NumberInput, PasswordInput, Select, Switch, TagsInput, Text, TextInput, Tooltip } from '@mantine/core'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { SettingSource } from '@/api/types'

import type { Value } from './values'

/** One input for a setting's type; the row around it carries the label and help. */
export function Input({ id, helpId, type, value, onChange, disabled, placeholder, min, max, options, secretSet }: {
  id: string; helpId?: string; type: string; value: Value; onChange: (v: Value) => void; disabled?: boolean
  placeholder?: string; min?: number | null; max?: number | null; options?: { value: string; label: string }[] | null
  secretSet?: boolean
}) {
  const { t } = useTranslation()
  const common = { id, disabled, 'aria-describedby': helpId, w: '100%' }
  if (type === 'int') {
    return <NumberInput {...common} placeholder={placeholder} min={min ?? undefined} max={max ?? undefined} allowDecimal={false}
      value={typeof value === 'number' ? value : value === null || value === '' ? '' : Number(value)}
      onChange={(v) => onChange(v === '' ? null : Number(v))} />
  }
  if (type === 'bool') return <Switch id={id} disabled={disabled} aria-describedby={helpId} checked={value === true} onChange={(e) => onChange(e.currentTarget.checked)} />
  if (type === 'choice') return <Select {...common} data={options ?? []} value={value === null ? null : String(value)} clearable placeholder={placeholder} onChange={(v) => onChange(v)} />
  if (['list', 'names', 'cidrs', 'ips'].includes(type)) {
    return <TagsInput {...common} placeholder={placeholder} value={Array.isArray(value) ? value : []} onChange={(v) => onChange(v.length ? v : null)} />
  }
  if (type === 'secret') {
    return <PasswordInput {...common} autoComplete="new-password" placeholder={secretSet ? t('agents.cfg.secretSet') : placeholder}
      value={typeof value === 'string' ? value : ''} onChange={(e) => onChange(e.currentTarget.value || null)} />
  }
  return <TextInput {...common} spellCheck={false} placeholder={placeholder} value={typeof value === 'string' || typeof value === 'number' ? String(value) : ''}
    onChange={(e) => onChange(e.currentTarget.value === '' ? null : e.currentTarget.value)} />
}

/** Where a value comes from, said only when it isn't the default, like Settings' rows; the env var sits in a tooltip. */
export function Source({ source, env }: { source: SettingSource; env?: string | null }) {
  const { t } = useTranslation()
  if (source === 'default') return null
  const text = <Text size="xs" c="dimmed" data-source={source}>{t(`agents.cfg.source.${source}`)}</Text>
  return source === 'env' && env
    ? <Tooltip label={t('agents.cfg.envTip', { env })} withArrow multiline maw={320}><span tabIndex={0}>{text}</span></Tooltip>
    : text
}

/** A settings row: label, help and state on the left, the control on the right (the shared .fb-setting-row). */
export function Row({ id, label, help, dirty, onUndo, onReset, tags, children }: {
  id: string; label: ReactNode; help?: ReactNode; dirty: boolean; onUndo: () => void; onReset?: () => void
  tags?: ReactNode; children: ReactNode
}) {
  const { t } = useTranslation()
  return (
    <div className="fb-setting-row" data-key={id}>
      <div className="fb-setting-about">
        <Text component="label" htmlFor={id} size="sm" fw={500}>{label}</Text>
        {help && <Text id={`${id}-help`} size="xs" c="dimmed">{help}</Text>}
        <Group gap="xs" mt={2}>
          {dirty ? <>
            <Badge size="sm" variant="light" color="warn" tt="none">{t('settings.unsaved')}</Badge>
            <Anchor component="button" type="button" size="xs" onClick={onUndo}>{t('settings.undo')}</Anchor>
          </> : <>
            {tags}
            {onReset && <Anchor component="button" type="button" size="xs" onClick={onReset}>{t('settings.reset')}</Anchor>}
          </>}
        </Group>
      </div>
      <div className="fb-setting-control">{children}</div>
    </div>
  )
}

