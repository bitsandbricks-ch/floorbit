import { ActionIcon, Menu, Tooltip } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconDownload, IconFileTypePdf, IconPhoto, IconVectorBezier2 } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { download, fileName, inlineImages, standaloneSvg, svgToPng } from './exportImage'

/** The top bar's export: the view on screen as a PNG or SVG (in the theme it is shown in), or the
 *  print sheet of the whole hall, which prints, saves as PDF and saves pictures in print colours. */
export function ExportMenu({ hall, hallName, filter }: { hall: string; hallName: string; filter: string }) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const save = async (as: 'png' | 'svg') => {
    const svg = document.querySelector<SVGSVGElement>('.fb-ws svg.fb-plan')
    if (!svg) return
    setBusy(true)
    try {
      const out = standaloneSvg(svg, Math.max(1600, svg.clientWidth * 2))
      const text = await inlineImages(out.text)
      const page = getComputedStyle(document.body).backgroundColor || '#fff'
      const blob = as === 'svg' ? new Blob([text], { type: 'image/svg+xml' }) : await svgToPng(text, out.width, out.height, page)
      download(blob, fileName(hallName, as))
    } catch {
      notifications.show({ color: 'down', message: t('plan.print.imageFailed') })
    } finally {
      setBusy(false)
    }
  }
  return (
    <Menu position="bottom-end" withinPortal width={250}>
      <Menu.Target>
        <Tooltip label={t('plan.export.title')}>
          <ActionIcon variant="default" size="md" aria-label={t('plan.export.title')} loading={busy}><IconDownload size={16} aria-hidden="true" /></ActionIcon>
        </Tooltip>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>{t('plan.export.view')}</Menu.Label>
        <Menu.Item leftSection={<IconPhoto size={14} />} onClick={() => void save('png')}>{t('plan.print.png')}</Menu.Item>
        <Menu.Item leftSection={<IconVectorBezier2 size={14} />} onClick={() => void save('svg')}>{t('plan.print.svg')}</Menu.Item>
        <Menu.Divider />
        <Menu.Label>{t('plan.export.hall')}</Menu.Label>
        <Menu.Item leftSection={<IconFileTypePdf size={14} />} component="a"
          href={`/plan?print=1&hall=${encodeURIComponent(hall)}${filter !== 'all' ? `&show=${filter}` : ''}`}>{t('plan.export.sheet')}</Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )
}
