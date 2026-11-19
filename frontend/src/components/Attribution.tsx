import { useTranslation } from 'react-i18next'
import { VersionInfo } from './VersionInfo'

// Same as templates/_attribution.html; its styles come from static/css/attribution.css.
/** ``compact`` for pages without a footer (the floor plan workspace), where it sits in a corner.
 *  ``version`` adds the line saying which Floorbit runs here (crew pages, not the public ones). */
export function Attribution({ compact = false, version = false }: { compact?: boolean; version?: boolean }) {
  const { t } = useTranslation()
  return (
    <div className={compact ? 'fb-attribution fb-attribution--compact' : 'fb-attribution'}>
      <a className="fb-pill fb-pill--coffee" href="https://buymeacoffee.com/bitsandbricks" target="_blank" rel="noopener noreferrer">
        <span aria-hidden="true">☕</span> {t('common.coffee')}
      </a>
      <a className="fb-pill fb-pill--bnb" href="https://bitsandbricks.ch" target="_blank" rel="noopener noreferrer">
        {t('common.poweredBy')} <strong>bitsandbricks.ch</strong>
      </a>
      {version && <VersionInfo />}
    </div>
  )
}
