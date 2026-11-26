import type { PlanDrawing } from './plan'

/** Wi-Fi view (issue #98). Client counts only. */
export type WifiBand = '2.4' | '5' | '6'
export interface WifiRadio { band: WifiBand; channel: number | null; width: number | null; utilization: number | null; clients: number }
export interface WifiAp {
  name: string; model: string; status: 'up' | 'down'; clients: number; radios: WifiRadio[]; source: string
  placed: boolean; on_plan: boolean; px: number | null; py: number | null; busy: boolean
}
export interface WifiData {
  aps: WifiAp[]; clients: number; up: number; down: string[]; busy: string[]
  overlaps: { band: WifiBand; channel: number; aps: [string, string] }[]
  bands: Partial<Record<WifiBand, { clients: number; radios: number; utilization: number | null }>>
  sources: string[]; errors: string[]; thresholds: { busy: number; crowded: number }
  drawing: PlanDrawing | null; hall: string; halls: { id: string; name: string }[]
  /** A controller streams to Telemetry, so clients over time are kept (GET /api/wifi/history). */
  history?: boolean
}
