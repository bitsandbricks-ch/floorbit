import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button, Code, Stack, Text, Title } from '@mantine/core'
import { IconAlertTriangle, IconRefresh } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { isStaleCode } from '@/lib/staleCode'

const RELOADED = 'fb-reloaded-for-update'

function reloadOnceForUpdate(): boolean {
  try {
    if (sessionStorage.getItem(RELOADED)) return false
    sessionStorage.setItem(RELOADED, '1')
  } catch {
    return false   // no storage: let the person press Reload instead of looping
  }
  window.location.reload()
  return true
}

function Fallback({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const { t } = useTranslation()
  const stale = isStaleCode(error)
  return (
    <div className="fb-page" role="alert">
      <Stack gap="sm" maw={560}>
        <IconAlertTriangle size={32} aria-hidden="true" color="var(--mantine-color-orange-6)" />
        <Title order={2}>{t(stale ? 'crash.updatedTitle' : 'crash.title')}</Title>
        <Text>{t(stale ? 'crash.updatedText' : 'crash.text')}</Text>
        <div>
          <Button leftSection={<IconRefresh size={16} aria-hidden="true" />} onClick={() => window.location.reload()}>
            {t('crash.reload')}
          </Button>
          {!stale && <Button variant="subtle" ml="xs" onClick={onRetry}>{t('crash.retry')}</Button>}
        </div>
        {!stale && (
          <details>
            <summary>{t('crash.details')}</summary>
            <Code block mt="xs">{String((error as Error)?.message ?? error).slice(0, 500)}</Code>
          </details>
        )}
      </Stack>
    </div>
  )
}

type Props = { children: ReactNode; resetKey?: string }
type State = { error: unknown; key?: string }

/** One page that throws while drawing shows this in the page area instead of a blank window: the
 *  sidebar stays, so the crew can go on to another page. A new page (``resetKey``) starts over. */
export class PageError extends Component<Props, State> {
  state: State = { error: null, key: this.props.resetKey }

  static getDerivedStateFromError(error: unknown): Partial<State> {
    return { error }
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey !== state.key ? { error: null, key: props.resetKey } : null
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    // After an update the open tab asks for code that is gone: one reload fetches the new version.
    if (isStaleCode(error) && reloadOnceForUpdate()) return
    console.error('[floorbit] page failed', error, info.componentStack)
  }

  render() {
    if (this.state.error) return <Fallback error={this.state.error} onRetry={() => this.setState({ error: null })} />
    return this.props.children
  }
}
