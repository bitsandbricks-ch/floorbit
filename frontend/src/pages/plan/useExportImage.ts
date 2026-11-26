import { notifications } from '@mantine/notifications'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { download, fileName, inlineImages, standaloneSvg, svgToPng } from './exportImage'

/** Saves the plan on screen as a PNG or SVG picture. */
export function useExportImage(hallName: string) {
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
  return { busy, save: (as: 'png' | 'svg') => void save(as) }
}
