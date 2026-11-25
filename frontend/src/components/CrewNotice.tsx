import { AnnouncementBadge, AnnouncementEditor, type Announcement } from '@bitsandbricks/ui'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useNotice } from '@/api/queries'
import type { CrewNotice } from '@/api/types'

const READ_KEY = 'floorbit-notice-hidden'

// Floorbit's notice times are Unix seconds; the shared badge takes milliseconds.
function asAnnouncement(n: CrewNotice | null | undefined): Announcement | null {
  return n ? { ...n, at: n.at * 1000, until: n.until ? n.until * 1000 : null } : null
}

// Before the shared badge, "read" was saved as the notice's time in seconds: keep it read.
try {
  const old = Number(localStorage.getItem(READ_KEY))
  if (old && old < 1e11) localStorage.setItem(READ_KEY, String(new Date(old * 1000).getTime()))
} catch {
  /* storage blocked */
}

function useTakeDown(after?: () => void) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => del<{ notice: null }>('/api/notice'),
    onSuccess: (data) => { client.setQueryData(qk.notice, data); after?.() },
  })
}

/** The crew notice as a badge in the top bar (issue #1006), the shared AnnouncementBadge: leads
 *  (incidents.assign) also get Change and Take down. */
export function CrewNoticeBadge({ compact }: { compact?: boolean }) {
  const { t } = useTranslation()
  const notice = useNotice().data?.notice
  const lead = useCan('incidents.assign')
  const [editing, setEditing] = useState(false)
  const remove = useTakeDown()
  return (
    <>
      <AnnouncementBadge notice={asAnnouncement(notice)} compact={compact} storageKey={READ_KEY} title={t('notice.title')}
        onEdit={lead ? () => setEditing(true) : undefined} onTakeDown={lead ? () => remove.mutate() : undefined}
        takingDown={remove.isPending} error={remove.error?.message} />
      {editing && <CrewNoticeEditor onClose={() => setEditing(false)} />}
    </>
  )
}

/** Leads put up or take down the notice (incidents.assign; the server checks it too). */
export function CrewNoticeEditor({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const current = useNotice().data?.notice
  const save = useMutation({
    mutationFn: (draft: { text: string; level: 'info' | 'warn'; hours: number }) => put<{ notice: CrewNotice }>('/api/notice', draft),
    onSuccess: (data) => { client.setQueryData(qk.notice, data); onClose() },
  })
  const remove = useTakeDown(onClose)
  return (
    <AnnouncementEditor opened current={asAnnouncement(current)} intro={t('notice.intro')} onClose={onClose}
      onSave={(draft) => save.mutate(draft)} saving={save.isPending}
      onTakeDown={() => remove.mutate()} takingDown={remove.isPending}
      error={(save.error ?? remove.error)?.message} />
  )
}
