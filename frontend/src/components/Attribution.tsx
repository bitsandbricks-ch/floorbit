import { useTranslation } from 'react-i18next'

// Same as templates/_attribution.html; its styles come from static/css/attribution.css.
export function Attribution() {
  const { t } = useTranslation()
  return (
    <div className="fb-attribution">
      <a className="fb-pill fb-pill--coffee" href="https://buymeacoffee.com/bitsandbricks" target="_blank" rel="noopener noreferrer">
        <span aria-hidden="true">☕</span> {t('common.coffee')}
      </a>
      <a className="fb-pill fb-pill--bnb" href="https://bitsandbricks.ch" target="_blank" rel="noopener noreferrer">
        {t('common.poweredBy')} <strong>bitsandbricks.ch</strong>
      </a>
    </div>
  )
}
