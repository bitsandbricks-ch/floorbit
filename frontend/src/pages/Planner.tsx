import {
  Alert, Badge, Button, Code, Group, Loader, Modal, NumberInput, Paper, ScrollArea, Select, SimpleGrid, Stack, Table, Text,
  TextInput, Textarea, Title,
} from '@mantine/core'
import { IconDownload, IconFileTypePdf, IconPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { PlannerData, PlannerModel, PlannerSettings, PlannedSwitch } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { seatRange } from './planner/seats'

function SettingsForm({ initial, models, onSaved }: { initial: PlannerSettings; models: PlannerModel[]; onSaved: () => void }) {
  const { t } = useTranslation()
  const [s, setS] = useState(initial)
  const set = <K extends keyof PlannerSettings>(k: K, v: PlannerSettings[K]) => setS((old) => ({ ...old, [k]: v }))
  const num = (k: 'access_ports' | 'uplink_ports' | 'spare' | 'vlan_base' | 'mgmt_first' | 'mgmt_vlan') =>
    (v: string | number) => set(k, typeof v === 'number' ? v : Number(v) || 0)
  const save = useMutation({ mutationFn: () => put<PlannerSettings>('/api/planner/settings', s), onSuccess: onSaved })
  return (
    <Stack gap="sm">
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
        <Select label={t('planner.model')} data={models.map((m) => ({ value: m.id, label: m.label }))} value={s.model}
          onChange={(v) => v && set('model', v)} allowDeselect={false} />
        <NumberInput label={t('planner.accessPorts')} value={s.access_ports} min={4} max={96} onChange={num('access_ports')} />
        <NumberInput label={t('planner.uplinkPorts')} value={s.uplink_ports} min={0} max={8} onChange={num('uplink_ports')} />
        <NumberInput label={t('planner.spare')} description={t('planner.spareHelp')} value={s.spare} min={0} max={24} onChange={num('spare')} />
        <Select label={t('planner.vlanMode')} value={s.vlan_mode} allowDeselect={false}
          data={(['block', 'hall', 'one'] as const).map((v) => ({ value: v, label: t(`planner.vlan.${v}`) }))}
          onChange={(v) => v && set('vlan_mode', v as PlannerSettings['vlan_mode'])} />
        <NumberInput label={t('planner.vlanBase')} value={s.vlan_base} min={2} max={4000} onChange={num('vlan_base')} />
        <TextInput label={t('planner.namePattern')} description={t('planner.namePatternHelp')} value={s.name}
          onChange={(e) => set('name', e.currentTarget.value)} />
        <NumberInput label={t('planner.mgmtVlan')} value={s.mgmt_vlan} min={1} max={4094} onChange={num('mgmt_vlan')} />
        <TextInput label={t('planner.mgmtNet')} placeholder="10.10.0.0/24" value={s.mgmt_net}
          onChange={(e) => set('mgmt_net', e.currentTarget.value)} />
        <NumberInput label={t('planner.mgmtFirst')} value={s.mgmt_first} min={1} onChange={num('mgmt_first')} />
        <TextInput label={t('planner.mgmtGateway')} placeholder="10.10.0.1" value={s.mgmt_gateway}
          onChange={(e) => set('mgmt_gateway', e.currentTarget.value)} />
      </SimpleGrid>
      {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
      <Group justify="flex-end">
        <Button loading={save.isPending} onClick={() => save.mutate()}>{t('planner.savePlan')}</Button>
      </Group>
    </Stack>
  )
}

function ConfigModal({ name, onClose }: { name: string; onClose: () => void }) {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: qk.plannerConfig(name), queryFn: () => get<{ config: string }>(`/api/planner/config/${encodeURIComponent(name)}`) })
  return (
    <Modal opened onClose={onClose} title={t('planner.configOf', { name })} size="xl">
      {q.error && <Alert color="down" role="alert">{q.error.message}</Alert>}
      {q.isPending ? <Loader aria-label={t('common.loading')} /> : q.data && (
        <ScrollArea h={480}><Code block>{q.data.config}</Code></ScrollArea>
      )}
    </Modal>
  )
}

function TemplateModal({ base, onClose, onSaved }: { base: PlannerModel; onClose: () => void; onSaved: (id: string) => void }) {
  const { t } = useTranslation()
  const full = useQuery({ queryKey: qk.plannerTemplate(base.id), queryFn: () => get<PlannerModel>(`/api/planner/templates/${base.id}`) })
  const [id, setId] = useState(base.builtin ? `${base.id}-custom` : base.id)
  const [label, setLabel] = useState(base.builtin ? `${base.label} (custom)` : base.label)
  const [access, setAccess] = useState(base.access)
  const [uplink, setUplink] = useState(base.uplink)
  const [text, setText] = useState<string | null>(null)
  const body = text ?? full.data?.text ?? ''
  const save = useMutation({
    mutationFn: () => put<PlannerModel>(`/api/planner/templates/${id}`, { label, access, uplink, text: body }),
    onSuccess: (m) => onSaved(m.id),
  })
  return (
    <Modal opened onClose={onClose} title={t('planner.editTemplate')} size="xl">
      <Stack gap="sm">
        <Group grow>
          <TextInput label={t('planner.templateId')} value={id} onChange={(e) => setId(e.currentTarget.value)} />
          <TextInput label={t('planner.templateLabel')} value={label} onChange={(e) => setLabel(e.currentTarget.value)} />
        </Group>
        <Group grow>
          <TextInput label={t('planner.accessPattern')} value={access} onChange={(e) => setAccess(e.currentTarget.value)} />
          <TextInput label={t('planner.uplinkPattern')} value={uplink} onChange={(e) => setUplink(e.currentTarget.value)} />
        </Group>
        <Textarea label={t('planner.templateText')} description={t('planner.templateHelp')} value={body} autosize minRows={12} maxRows={24}
          styles={{ input: { fontFamily: 'var(--mantine-font-family-monospace)', fontSize: 12 } }} onChange={(e) => setText(e.currentTarget.value)} />
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={save.isPending} disabled={!body.trim()} onClick={() => save.mutate()}>{t('planner.saveTemplate')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function SwitchRow({ sw, onShow }: { sw: PlannedSwitch; onShow: () => void }) {
  const { t } = useTranslation()
  return (
    <Table.Tr>
      <Table.Td fw={600}>{sw.name}</Table.Td>
      <Table.Td>{seatRange(sw.ports.map((p) => p.seat))}</Table.Td>
      <Table.Td>{t('planner.portsUsed', { used: sw.ports.length, spare: sw.spare.length })}</Table.Td>
      <Table.Td>{sw.vlan}</Table.Td>
      <Table.Td>{sw.mgmt_ip ?? '–'}</Table.Td>
      <Table.Td>
        <Badge variant="light" color={sw.exists ? 'up' : 'trace'} tt="none">{sw.exists ? t('planner.exists') : t('planner.new')}</Badge>
      </Table.Td>
      <Table.Td><Button size="compact-xs" variant="default" onClick={onShow}>{t('planner.showConfig')}</Button></Table.Td>
    </Table.Tr>
  )
}

/** Before the event: switches, ports and VLANs per seat block, then configs and cable labels. */
export default function Planner() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.planner, queryFn: () => get<PlannerData>('/api/planner') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.planner })
  useLiveEvent('data.changed', refresh)
  const [config, setConfig] = useState<string | null>(null)
  const [editing, setEditing] = useState<PlannerModel | null>(null)
  const [copies, setCopies] = useState('2')
  const [added, setAdded] = useState<string[] | null>(null)
  const apply = useMutation({ mutationFn: () => post<{ added: string[] }>('/api/planner/apply'), onSuccess: (r) => { setAdded(r.added); refresh() } })
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/planner/templates/${id}`), onSuccess: refresh })
  const d = query.data
  const plan = d?.plan
  const model = d && plan ? d.models.find((m) => m.id === plan.settings.model) : undefined

  return (
    <Layout title={t('planner.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('planner.title')} desc={t('planner.intro')} />
      <Stack gap="md">
        {(query.error ?? apply.error ?? remove.error) && (
          <Alert color="down" role="alert">{t('common.error', { message: (query.error ?? apply.error ?? remove.error)!.message })}</Alert>
        )}
        {added && (
          <Alert color="up" role="status" withCloseButton onClose={() => setAdded(null)}>
            {added.length ? t('planner.added', { count: added.length, names: added.join(', ') }) : t('planner.addedNone')}
          </Alert>
        )}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : d && plan && (
          <>
            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{t('planner.settings')}</Title>
              <SettingsForm key={JSON.stringify(plan.settings)} initial={plan.settings} models={d.models} onSaved={refresh} />
            </Paper>

            {plan.problems.map((p) => <Alert key={p} color="warn">{p}</Alert>)}
            <SimpleGrid cols={{ base: 2, sm: 5 }}>
              {(['seats', 'switches', 'new', 'vlans', 'uplinks'] as const).map((k) => (
                <Paper key={k} withBorder radius="lg" p="sm">
                  <Text size="xs" c="dimmed">{t(`planner.totals.${k}`)}</Text>
                  <Text fz={26} fw={700}>{plan.totals[k]}</Text>
                </Paper>
              ))}
            </SimpleGrid>

            {plan.blocks.length === 0 ? (
              <Paper withBorder radius="lg" p="lg"><Text c="dimmed">{t('planner.noBlocks')}</Text></Paper>
            ) : (
              <Paper withBorder radius="lg" p="md">
                <Group justify="space-between" mb="xs" wrap="wrap">
                  <Title order={2} size="h4">{t('planner.switches')}</Title>
                  <Group gap="xs">
                    <Button size="xs" variant="default" component="a" href="/api/planner/configs.zip" leftSection={<IconDownload size={14} />}>
                      {t('planner.configs')}
                    </Button>
                    <Button size="xs" variant="default" component="a" href="/api/planner/plan.csv" leftSection={<IconDownload size={14} />}>
                      {t('planner.csv')}
                    </Button>
                    <Select size="xs" w={140} aria-label={t('planner.copies')} value={copies} allowDeselect={false}
                      data={['1', '2'].map((v) => ({ value: v, label: t('planner.copiesN', { count: Number(v) }) }))}
                      onChange={(v) => v && setCopies(v)} />
                    <Button size="xs" variant="default" component="a" href={`/api/planner/labels.pdf?copies=${copies}`}
                      leftSection={<IconFileTypePdf size={14} />}>
                      {t('planner.labels')}
                    </Button>
                    {plan.totals.new > 0 && (
                      <ConfirmButton size="xs" label={t('planner.apply', { count: plan.totals.new })}
                        question={t('planner.applyQuestion', { count: plan.totals.new })} onConfirm={() => apply.mutate()} />
                    )}
                  </Group>
                </Group>
                <Table.ScrollContainer minWidth={760}>
                  <Table striped>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>{t('planner.switch')}</Table.Th><Table.Th>{t('planner.seats')}</Table.Th><Table.Th>{t('planner.ports')}</Table.Th>
                        <Table.Th>VLAN</Table.Th><Table.Th>{t('planner.mgmtIp')}</Table.Th><Table.Th>{t('planner.state')}</Table.Th><Table.Th />
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {plan.switches.map((sw) => <SwitchRow key={sw.name} sw={sw} onShow={() => setConfig(sw.name)} />)}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              </Paper>
            )}

            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb={4}>{t('planner.models')}</Title>
              <Text size="sm" c="dimmed" mb="sm">{t('planner.modelsHelp')}</Text>
              <Stack gap="xs">
                {d.models.map((m) => (
                  <Group key={m.id} justify="space-between" wrap="nowrap">
                    <Stack gap={0} style={{ minWidth: 0 }}>
                      <Text fw={600}>{m.label} {m.id === model?.id && <Badge size="xs" variant="light" tt="none">{t('planner.inUse')}</Badge>}</Text>
                      <Text size="xs" c="dimmed"><Code>{m.access}</Code> · <Code>{m.uplink}</Code></Text>
                    </Stack>
                    <Group gap="xs" wrap="nowrap">
                      <Button size="xs" variant="default" leftSection={m.builtin ? <IconPlus size={14} /> : undefined} onClick={() => setEditing(m)}>
                        {m.builtin ? t('planner.copyModel') : t('planner.editModel')}
                      </Button>
                      {!m.builtin && (
                        <ConfirmButton size="xs" variant="subtle" danger label={t('planner.removeModel')}
                          question={t('planner.removeQuestion', { name: m.label })} onConfirm={() => remove.mutate(m.id)} />
                      )}
                    </Group>
                  </Group>
                ))}
              </Stack>
            </Paper>
          </>
        )}
      </Stack>
      {config && <ConfigModal name={config} onClose={() => setConfig(null)} />}
      {editing && <TemplateModal base={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh() }} />}
    </Layout>
  )
}
