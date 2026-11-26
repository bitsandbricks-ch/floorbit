import { ActionIcon, Menu, Tooltip } from '@mantine/core'
import { IconDownload, IconFileTypePdf, IconPhoto, IconVectorBezier2 } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { useExportImage } from './useExportImage'

/** The top bar's export: the view on screen as a PNG or SVG (in the theme it is shown in), or the
 *  print sheet of the whole hall, which prints, saves as PDF and saves pictures in print colours. */
export function ExportMenu({ hall, hallName, filter }: { hall: string; hallName: string; filter: string }) {
  const { t } = useTranslation()
  const { busy, save } = useExportImage(hallName)
  return (
    <Menu position="bottom-end" withinPortal width={250}>
      <Menu.Target>
        <Tooltip label={t('plan.export.title')}>
          <ActionIcon variant="default" size="md" aria-label={t('plan.export.title')} loading={busy}><IconDownload size={16} aria-hidden="true" /></ActionIcon>
        </Tooltip>
      </Menu.Target>
      <Menu.Dropdown>
        <ExportItems hall={hall} filter={filter} save={save} />
      </Menu.Dropdown>
    </Menu>
  )
}

/** The export's menu entries, also in the phone plan's More menu. */
export function ExportItems({ hall, filter, save }: { hall: string; filter: string; save: (as: 'png' | 'svg') => void }) {
  const { t } = useTranslation()
  return (
    <>
      <Menu.Label>{t('plan.export.view')}</Menu.Label>
      <Menu.Item leftSection={<IconPhoto size={14} />} onClick={() => save('png')}>{t('plan.print.png')}</Menu.Item>
      <Menu.Item leftSection={<IconVectorBezier2 size={14} />} onClick={() => save('svg')}>{t('plan.print.svg')}</Menu.Item>
      <Menu.Divider />
      <Menu.Label>{t('plan.export.hall')}</Menu.Label>
      <Menu.Item leftSection={<IconFileTypePdf size={14} />} component="a"
        href={`/plan?print=1&hall=${encodeURIComponent(hall)}${filter !== 'all' ? `&show=${filter}` : ''}`}>{t('plan.export.sheet')}</Menu.Item>
    </>
  )
}
