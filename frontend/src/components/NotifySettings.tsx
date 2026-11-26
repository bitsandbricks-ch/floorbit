import { NotifySettings as SharedSettings } from '@bitsandbricks/ui'
import { useTranslation } from 'react-i18next'
import { crewNotify } from '@/notify/crewNotify'

/** Browser notifications for this device (issue #154): the shared settings with Floorbit's kinds.
 *  A job sent to me is urgent, so it can come through quiet hours. */
export function NotifySettings({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <SharedSettings store={crewNotify} opened={opened} onClose={onClose} intro={t('common.notify.intro')}
      kinds={[
        { id: 'jobs', label: t('common.notify.jobs'), urgent: true },
        { id: 'incidents', label: t('common.notify.incidents') },
        { id: 'switches', label: t('common.notify.switches') },
        { id: 'services', label: t('common.notify.services') },
      ]} />
  )
}
