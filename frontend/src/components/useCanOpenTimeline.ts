import { useCan, useFeature } from '@/api/queries'

/** The full changelog link: only where the page is on and the account may read the audit log. */
export function useCanOpenTimeline() {
  const on = useFeature('timeline')
  const may = useCan('audit.read')
  return on && may
}
