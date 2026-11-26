import { Anchor, Button, Code, Group, Stack, Text, TextInput } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Application } from '@/api/applications'
import { MAX_URL, download, gamesFile, rulesFile, shareUrl, sharedEntry } from '@/api/applicationShare'
import { FormDialog } from '@bitsandbricks/ui'

/** Share one application (issue #1612): what leaves, what it matched here today, then a pull request
 *  on Floorbit's own list (GitHub opens with the file filled in) or a rules file for another event. */
export function ShareApplication({ app, onClose }: { app: Application; onClose: () => void }) {
  const { t } = useTranslation()
  const [source, setSource] = useState('')
  const entry = sharedEntry(app, true)
  const url = shareUrl(entry, source)
  const tooLong = url.length > MAX_URL
  const ready = source.trim().length > 0
  const seen = app.seen

  return (
    <FormDialog open onClose={onClose} title={t('applicationShare.title', { name: app.name })} subtitle={t('applicationShare.intro')} wide
      footer={(
        <Group justify="flex-end" gap="xs">
          <Button variant="default" onClick={() => download(`${app.id}.json`, rulesFile([sharedEntry(app)]))}>
            {t('applicationShare.download')}
          </Button>
          <Button component="a" href={ready && !tooLong ? url : undefined} target="_blank" rel="noopener noreferrer"
            disabled={!ready || tooLong}>
            {t('applicationShare.openGithub')}
          </Button>
        </Group>
      )}>
      <Stack gap="sm">
        <TextInput label={t('applicationShare.source')} description={t('applicationShare.sourceHelp')} required
          value={source} maxLength={300} onChange={(e) => setSource(e.currentTarget.value)}
          placeholder="https://example.com/support/ports" />
        <div>
          <Text size="sm" fw={500} mb={4}>{t('applicationShare.preview')}</Text>
          <Code block aria-label={t('applicationShare.preview')} style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{gamesFile(entry, source || '…')}</Code>
          <Text size="xs" c="dimmed" mt={4}>{t('applicationShare.onlyMatches')}</Text>
          {entry.category !== app.category && (
            <Text size="xs" c="dimmed" mt={4}>{t('trafficCategories.sharedAsOther')}</Text>
          )}
        </div>
        <Text size="sm" aria-label={t('applicationShare.tryTitle')}>
          {!seen.seats ? t('applicationShare.triedNone')
            : seen.lookups ? t('applicationShare.triedLookups', { lookups: seen.lookups, seats: seen.seats })
            : t('applicationShare.tried', { seats: seen.seats })}
        </Text>
        {tooLong && <Text size="sm" c="var(--bnb-warn)">{t('applicationShare.tooLong')}</Text>}
        <Text size="xs" c="dimmed">
          {t('applicationShare.review')}{' '}
          <Anchor href="https://github.com/bitsandbricks-ch/floorbit-plugins/tree/main/games" target="_blank" rel="noopener noreferrer" size="xs">
            bitsandbricks-ch/floorbit-plugins
          </Anchor>
        </Text>
      </Stack>
    </FormDialog>
  )
}
