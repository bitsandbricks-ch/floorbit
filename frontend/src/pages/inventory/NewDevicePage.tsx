import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { useInventory } from '@/api/queries'
import type { Device } from '@/api/types'
import { ItemPage } from '@/components/ItemPage'
import { Panel } from '@/components/ui'
import { DeviceForm } from './DeviceForm'
import { devicePath } from './model'
import { useInventoryGroups } from './scope'

/** A new device on a page of its own (/inventory/devices/new, issue #877): once added, its own
 *  page opens. */
export default function NewDevicePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const client = useQueryClient()
  const inventory = useInventory(false).data
  const overview = useInventoryGroups().data
  const [error, setError] = useState<string | null>(null)
  const sourceName = (sid: string) => inventory?.sources.find((s) => s.id === sid)?.name ?? sid
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) => post<Device>('/api/inventory', body),
    onSuccess: (device) => { void client.invalidateQueries({ queryKey: qk.inventoryAll }); navigate(devicePath(device.id), { replace: true }) },
    onError: (e) => setError(e.message),
  })
  return (
    <ItemPage title={t('inventory.newDevice')} fallbackTitle={t('inventory.title')}
      back={{ href: '/inventory', label: t('inventory.page.back') }} loading={!inventory || !overview}>
      {inventory && overview && (
        <Panel>
          <DeviceForm device={null} roles={inventory.roles} overview={overview} sourceName={sourceName}
            busy={add.isPending} error={error} onCancel={() => navigate('/inventory')}
            onSave={(body) => { setError(null); add.mutate(body) }} onUnlock={() => undefined} />
        </Panel>
      )}
    </ItemPage>
  )
}
