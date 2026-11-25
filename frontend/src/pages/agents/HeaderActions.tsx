import { ActionIcon, Button, Group, Menu } from '@mantine/core'
import { IconCertificate, IconDots, IconDownload, IconRefresh, IconSettings, IconTrash } from '@tabler/icons-react'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { qk } from '@/api/keys'
import type { Agent } from '@/api/types'
import { ConfirmModal } from '@bitsandbricks/ui'
import { RollKeyButton } from './AgentSettings'

/** The agent page's header actions (issue #905): check now, roll its key, and the rest under More. */
export function HeaderActions({ agent, onTab, onRevoke, revoking }: {
  agent: Agent; onTab: (tab: string) => void; onRevoke: () => void; revoking?: boolean
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [checking, setChecking] = useState(false)
  const [asking, setAsking] = useState(false)
  return (
    <Group gap="xs" wrap="nowrap">
      <Button size="compact-sm" variant="default" leftSection={<IconRefresh size={14} />} loading={checking}
        onClick={() => { setChecking(true); void qc.invalidateQueries({ queryKey: qk.agents }).finally(() => setChecking(false)) }}>{t('agentDetail.checkNow')}</Button>
      <RollKeyButton agent={agent} />
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <ActionIcon variant="default" size="md" aria-label={t('agentDetail.more')}><IconDots size={16} /></ActionIcon>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item leftSection={<IconSettings size={14} />} onClick={() => onTab('settings')}>{t('agentDetail.tab.settings')}</Menu.Item>
          <Menu.Item leftSection={<IconCertificate size={14} />} onClick={() => onTab('certificate')}>{t('agentDetail.tab.certificate')}</Menu.Item>
          <Menu.Item leftSection={<IconDownload size={14} />} component="a" href="/api/agents/ca.pem">{t('agents.cfg.downloadCa')}</Menu.Item>
          <Menu.Divider />
          <Menu.Item leftSection={<IconTrash size={14} />} color="down" onClick={() => setAsking(true)}>{t('agents.revoke')}</Menu.Item>
        </Menu.Dropdown>
      </Menu>
      <ConfirmModal open={asking} title={t('agents.revoke')} body={t('agents.revokeQuestion', { name: agent.name })}
        confirmLabel={t('agents.revoke')} loading={revoking} onClose={() => setAsking(false)}
        onConfirm={() => { setAsking(false); onRevoke() }} />
    </Group>
  )
}
