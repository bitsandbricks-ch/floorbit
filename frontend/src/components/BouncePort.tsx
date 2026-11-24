import { Button } from '@mantine/core'
import { IconPlugConnected } from '@tabler/icons-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { PortDialog, type PortRequest } from '@/pages/security/PortDialog'

interface PortInfo { available: boolean; needs_login: boolean; plugin: string | null }

/** Bounce a seat's switch port, with the tech's own switch login when the plugin needs one.
 *  Shown on the seat inspector and on a seat's incident, where "no internet" is usually first
 *  tried this way. Nothing shows without ports.act or a plugin that can do it. */
export function BouncePort({ seat, onBounced }: { seat: string; onBounced: (message: string) => void }) {
  const { t } = useTranslation()
  const canAct = useCan('ports.act')
  const info = useQuery({ queryKey: qk.ports, queryFn: () => get<PortInfo>('/api/ports'), enabled: canAct })
  const [request, setRequest] = useState<PortRequest | null>(null)
  const [error, setError] = useState<string | null>(null)
  const bounce = useMutation({
    mutationFn: (extra: Record<string, string | boolean | undefined>) => post<{ message: string }>('/api/ports/bounce', { seat, ...extra }),
    onSuccess: (r) => {
      setRequest(null)
      onBounced(r.message)
    },
    onError: (e) => setError(e.message),
  })
  if (!canAct || !info.data?.available) return null
  return (
    <>
      <Button size="xs" color="warn" variant="light" leftSection={<IconPlugConnected size={14} />}
        onClick={() => { setError(null); setRequest({ action: 'bounce', seat, where: t('plan.seat', { seat }) }) }}>
        {t('security.bounce')}
      </Button>
      <PortDialog request={request} needsLogin={!!info.data.needs_login} busy={bounce.isPending} error={error}
        onClose={() => setRequest(null)} onConfirm={(extra) => bounce.mutate(extra)} />
    </>
  )
}
