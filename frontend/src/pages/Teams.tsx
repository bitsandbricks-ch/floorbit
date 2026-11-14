import { ActionIcon, Alert, Badge, Button, Group, Loader, Paper, Select, Stack, Table, Text, TextInput, Title, Tooltip } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, patch, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useAccounts, useRoles, useTeams } from '@/api/queries'
import type { RoleInfo, Team } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { RoleForm, type RoleDraft } from './teams/RoleForm'

/** Settings > Roles and teams: custom roles, the team tree and who is in which team. Admins only. */
export default function Teams() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const roles = useRoles()
  const teams = useTeams()
  const accounts = useAccounts()
  const [editing, setEditing] = useState<RoleInfo | null>(null)
  const [formOpen, form] = useDisclosure(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [newTeam, setNewTeam] = useState('')

  const done = (text: string) => () => {
    void client.invalidateQueries({ queryKey: qk.roles })
    void client.invalidateQueries({ queryKey: qk.teams })
    setMessage({ ok: true, text })
  }
  const failed = (e: Error) => setMessage({ ok: false, text: e.message })

  const saveRole = useMutation({
    mutationFn: (d: RoleDraft) => put(`/api/roles/${encodeURIComponent(d.id)}`, d),
    onSuccess: () => {
      done(t('teams.roleSaved'))()
      form.close()
    },
    onError: (e) => setFormError(e.message),
  })
  const deleteRole = useMutation({ mutationFn: (id: string) => del(`/api/roles/${encodeURIComponent(id)}`), onSuccess: done(t('teams.roleDeleted')), onError: failed })
  const addTeam = useMutation({
    mutationFn: (v: { name: string; parent: string | null }) => post('/api/teams', v),
    onSuccess: () => {
      setNewTeam('')
      done(t('teams.teamAdded'))()
    },
    onError: failed,
  })
  const renameTeam = useMutation({ mutationFn: (v: { id: string; name: string }) => patch(`/api/teams/${v.id}`, { name: v.name }), onSuccess: done(t('teams.teamSaved')), onError: failed })
  const deleteTeam = useMutation({ mutationFn: (id: string) => del(`/api/teams/${id}`), onSuccess: done(t('teams.teamDeleted')), onError: failed })
  const setMember = useMutation({
    mutationFn: (v: { team: string; username: string; role: string | null }) =>
      v.role ? put(`/api/teams/${v.team}/members/${encodeURIComponent(v.username)}`, { role: v.role }) : del(`/api/teams/${v.team}/members/${encodeURIComponent(v.username)}`),
    onSuccess: done(t('teams.membersSaved')),
    onError: failed,
  })

  const roleOptions = (roles.data?.roles ?? []).map((r) => ({ value: r.id, label: r.label }))
  const error = roles.error ?? teams.error

  return (
    <Layout title={t('teams.title')} back={{ href: '/settings', label: t('common.settings') }}>
      <PageHead title={t('teams.title')} desc={t('teams.intro')} />
      <Text size="sm" role="status" mb="sm" className={message ? (message.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
        {message?.text}
      </Text>
      {error && (
        <Alert color="down" role="alert" mb="md">
          {t('common.error', { message: error.message })}
        </Alert>
      )}

      <Group justify="space-between" mt="lg" mb="xs">
        <Title order={2} size="h3">
          {t('teams.roles')}
        </Title>
        <Button leftSection={<IconPlus size={16} />} onClick={() => { setEditing(null); setFormError(null); form.open() }}>
          {t('teams.newRole')}
        </Button>
      </Group>
      {roles.isPending ? (
        <Loader size="sm" />
      ) : (
        <Paper withBorder radius="lg" style={{ overflowX: 'auto' }}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('teams.role')}</Table.Th>
                <Table.Th>{t('teams.permissions')}</Table.Th>
                <Table.Th>{t('teams.accounts')}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(roles.data?.roles ?? []).map((r) => (
                <Table.Tr key={r.id}>
                  <Table.Td>
                    <Group gap={6}>
                      <Text fw={600}>{r.label}</Text>
                      {r.builtin && (
                        <Badge size="xs" variant="light" color="gray">
                          {t('teams.builtin')}
                        </Badge>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">
                      {t(`teams.roleText.${r.id}`, { defaultValue: r.description })}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      {r.permissions.map((p) => (
                        <Badge key={p} size="sm" variant="outline" color="gray" tt="none">
                          {p}
                        </Badge>
                      ))}
                    </Group>
                  </Table.Td>
                  <Table.Td>{r.users}</Table.Td>
                  <Table.Td>
                    {!r.builtin && (
                      <Group gap={4} wrap="nowrap">
                        <Button size="xs" variant="default" onClick={() => { setEditing(r); setFormError(null); form.open() }}>
                          {t('teams.edit')}
                        </Button>
                        <ConfirmButton size="xs" variant="subtle" danger label={t('teams.delete')}
                          question={t('teams.deleteRoleQuestion', { role: r.label })} onConfirm={() => deleteRole.mutate(r.id)} />
                      </Group>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      )}

      <Title order={2} size="h3" mt="xl" mb="xs">
        {t('teams.teams')}
      </Title>
      <Text size="sm" c="dimmed" mb="sm">
        {t('teams.teamsIntro')}
      </Text>
      {teams.isPending ? (
        <Loader size="sm" />
      ) : (
        <Stack gap="xs">
          {(teams.data?.teams ?? []).map((team) => (
            <TeamRow key={team.id} team={team} roleOptions={roleOptions}
              accounts={(accounts.data?.users ?? []).map((u) => ({ value: u.username, label: u.display_name === u.username ? u.username : `${u.display_name} (${u.username})` }))}
              onRename={(name) => renameTeam.mutate({ id: team.id, name })}
              onAddSub={(name) => addTeam.mutate({ name, parent: team.id })}
              onDelete={() => deleteTeam.mutate(team.id)}
              onMember={(username, role) => setMember.mutate({ team: team.id, username, role })} />
          ))}
          <form onSubmit={(e) => { e.preventDefault(); if (newTeam.trim()) addTeam.mutate({ name: newTeam.trim(), parent: null }) }}>
            <Group gap="xs" mt="xs">
              <TextInput placeholder={t('teams.newTeamName')} aria-label={t('teams.newTeamName')} value={newTeam} onChange={(e) => setNewTeam(e.currentTarget.value)} maxLength={40} />
              <Button type="submit" variant="default" leftSection={<IconPlus size={16} />} disabled={!newTeam.trim()}>
                {t('teams.addTeam')}
              </Button>
            </Group>
          </form>
        </Stack>
      )}

      {roles.data && formOpen && (
        <RoleForm key={editing?.id ?? 'new'} role={editing} permissions={roles.data.permissions} opened={formOpen}
          busy={saveRole.isPending} error={formError} onClose={form.close} onSave={(d) => saveRole.mutate(d)} />
      )}
    </Layout>
  )
}

function TeamRow({
  team,
  roleOptions,
  accounts,
  onRename,
  onAddSub,
  onDelete,
  onMember,
}: {
  team: Team
  roleOptions: { value: string; label: string }[]
  accounts: { value: string; label: string }[]
  onRename: (name: string) => void
  onAddSub: (name: string) => void
  onDelete: () => void
  onMember: (username: string, role: string | null) => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(team.name)
  const [sub, setSub] = useState('')
  const [who, setWho] = useState<string | null>(null)
  const [role, setRole] = useState<string | null>('tech')
  const members = new Set(team.members.map((m) => m.username))
  return (
    <Paper withBorder radius="lg" p="sm" ml={team.depth * 28} aria-label={team.name}>
      <Group justify="space-between" wrap="wrap" gap="xs">
        <Group gap="xs">
          <TextInput size="xs" value={name} aria-label={t('teams.teamName')} maxLength={40} onChange={(e) => setName(e.currentTarget.value)}
            onBlur={() => name.trim() && name !== team.name && onRename(name.trim())} styles={{ input: { fontWeight: 600 } }} />
          {team.depth > 0 && (
            <Text size="xs" c="dimmed">
              {t('teams.subTeam')}
            </Text>
          )}
        </Group>
        <Group gap="xs">
          <TextInput size="xs" placeholder={t('teams.subTeamName')} aria-label={t('teams.subTeamName')} value={sub} maxLength={40} onChange={(e) => setSub(e.currentTarget.value)} />
          <Button size="xs" variant="default" disabled={!sub.trim()} onClick={() => { onAddSub(sub.trim()); setSub('') }}>
            {t('teams.addSubTeam')}
          </Button>
          <ConfirmButton size="xs" variant="subtle" danger label={t('teams.delete')} question={t('teams.deleteTeamQuestion', { team: team.name })} onConfirm={onDelete} />
        </Group>
      </Group>
      <Group gap={6} mt="xs">
        {team.members.length === 0 && (
          <Text size="sm" c="dimmed">
            {t('teams.noMembers')}
          </Text>
        )}
        {team.members.map((m) => (
          <Badge key={m.username} size="lg" variant="light" color="trace" tt="none"
            rightSection={
              <Tooltip label={t('teams.removeMember', { user: m.username })}>
                <ActionIcon size="xs" variant="transparent" color="gray" aria-label={t('teams.removeMember', { user: m.username })} onClick={() => onMember(m.username, null)}>
                  <IconTrash size={12} />
                </ActionIcon>
              </Tooltip>
            }>
            {m.username} · {m.role_label}
          </Badge>
        ))}
      </Group>
      <Group gap="xs" mt="xs">
        <Select size="xs" placeholder={t('teams.addMember')} aria-label={t('teams.addMember')} data={accounts.filter((a) => !members.has(a.value))} value={who} onChange={setWho} searchable />
        <Select size="xs" aria-label={t('teams.memberRole')} data={roleOptions} value={role} onChange={setRole} w={140} />
        <Button size="xs" variant="default" disabled={!who || !role} onClick={() => { if (who && role) onMember(who, role); setWho(null) }}>
          {t('teams.add')}
        </Button>
      </Group>
    </Paper>
  )
}
