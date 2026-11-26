import { Alert, Button, CopyButton, Group, Menu, Modal, Stack, Switch, Text, TextInput } from '@mantine/core'
import { IconBookmark, IconChevronDown, IconDeviceFloppy, IconLink, IconLock, IconRefresh, IconTrash } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, post, put } from '@/api/client'
import { PLAN_VIEWS_KEY, type PlanView, usePlanViews } from '@/api/planViews'
import { toastDone } from '@bitsandbricks/ui'
import type { View } from '../model'
import { applyView, currentView, VIEW_PARAM } from './apply'

/** The plan's View ▾ menu (issue #1326): saved views of this hall to open, and saving what the plan
 *  shows now (position and zoom, layers, filter) under a name. Opening one is an address with
 *  ``?pv=``, so a view also has a link. */
export function ViewMenu({ hall, view, params, setParams, setView, canEdit }: {
  hall: string; view: View | null; params: URLSearchParams
  setParams: (p: URLSearchParams) => void; setView: (v: View) => void; canEdit: boolean
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const views = usePlanViews().data ?? []
  const here = views.filter((v) => v.hall === hall)
  const openId = params.get(VIEW_PARAM)
  const open = views.find((v) => v.id === openId)
  const [saving, setSaving] = useState(false)

  // Move to the view's part of the hall once its hall is the one shown (a link, or picked here).
  const moved = useRef<string | null>(null)
  useEffect(() => {
    if (!open || open.hall !== hall || moved.current === open.id) return
    moved.current = open.id
    setView(open.view)
  }, [open, hall, setView])
  const pick = (v: PlanView) => { moved.current = null; setParams(applyView(params, v)) }

  const refresh = () => void qc.invalidateQueries({ queryKey: PLAN_VIEWS_KEY })
  const update = useMutation({
    mutationFn: (v: PlanView) => put<PlanView>(`/api/plan-views/${encodeURIComponent(v.id)}`, currentView(params, hall, view!, v.name, v.private)),
    onSuccess: (v) => { toastDone(t('planViews.updated', { name: v.name })); refresh() },
  })
  const remove = useMutation({
    mutationFn: (v: PlanView) => del(`/api/plan-views/${encodeURIComponent(v.id)}`),
    onSuccess: () => {
      const next = new URLSearchParams(params)
      next.delete(VIEW_PARAM)
      setParams(next)
      refresh()
    },
  })
  const link = `${window.location.origin}${window.location.pathname}?${params.toString()}`

  return (
    <>
      <Menu position="bottom-end" withinPortal width={280}>
        <Menu.Target>
          <Button size="xs" variant={open ? 'light' : 'default'} leftSection={<IconBookmark size={14} aria-hidden="true" />}
            rightSection={<IconChevronDown size={14} aria-hidden="true" />} maw={220}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{open ? open.name : t('planViews.button')}</span>
          </Button>
        </Menu.Target>
        <Menu.Dropdown>
          {here.length === 0 && <Menu.Label>{t('planViews.none')}</Menu.Label>}
          {here.map((v) => (
            <Menu.Item key={v.id} onClick={() => pick(v)} rightSection={v.private ? <IconLock size={12} aria-label={t('planViews.private')} /> : undefined}
              bg={v.id === openId ? 'var(--bnb-info-soft)' : undefined}>
              {v.name}
            </Menu.Item>
          ))}
          {(canEdit || open) && <Menu.Divider />}
          {canEdit && view && <Menu.Item leftSection={<IconDeviceFloppy size={14} />} onClick={() => setSaving(true)}>{t('planViews.save')}</Menu.Item>}
          {canEdit && open && view && (
            <Menu.Item leftSection={<IconRefresh size={14} />} onClick={() => update.mutate(open)}>{t('planViews.update', { name: open.name })}</Menu.Item>
          )}
          {open && (
            <CopyButton value={link} timeout={1500}>
              {({ copied, copy }) => (
                <Menu.Item leftSection={<IconLink size={14} />} closeMenuOnClick={false} onClick={copy}>
                  {copied ? t('planViews.copied') : t('planViews.copyLink')}
                </Menu.Item>
              )}
            </CopyButton>
          )}
          {canEdit && open && (
            <Menu.Item color="down" leftSection={<IconTrash size={14} />} onClick={() => remove.mutate(open)}>{t('planViews.delete', { name: open.name })}</Menu.Item>
          )}
        </Menu.Dropdown>
      </Menu>
      {(update.error || remove.error) && <Text size="xs" c="down" role="alert">{(update.error ?? remove.error)!.message}</Text>}
      {saving && view && <SaveViewDialog hall={hall} view={view} params={params} onClose={() => setSaving(false)}
        onSaved={(v) => { setSaving(false); moved.current = v.id; setParams(applyView(params, v)) }} />}
    </>
  )
}

function SaveViewDialog({ hall, view, params, onClose, onSaved }: {
  hall: string; view: View; params: URLSearchParams; onClose: () => void; onSaved: (v: PlanView) => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [priv, setPriv] = useState(false)
  const save = useMutation({
    mutationFn: () => post<PlanView>('/api/plan-views', currentView(params, hall, view, name.trim(), priv)),
    onSuccess: (v) => { toastDone(t('planViews.saved', { name: v.name })); void qc.invalidateQueries({ queryKey: PLAN_VIEWS_KEY }); onSaved(v) },
  })
  return (
    <Modal opened onClose={onClose} title={t('planViews.saveTitle')}>
      <Stack gap="sm">
        <TextInput label={t('planViews.name')} value={name} maxLength={60} required data-autofocus
          onChange={(e) => setName(e.currentTarget.value)} onKeyDown={(e) => { if (e.key === 'Enter' && name.trim()) save.mutate() }} />
        <Text size="sm" c="dimmed">{t('planViews.keeps')}</Text>
        <Switch label={t('planViews.onlyMe')} description={t('planViews.onlyMeHint')} checked={priv} onChange={(e) => setPriv(e.currentTarget.checked)} />
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>{t('planViews.saveButton')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}
