// The flow lookup (docs/flows.md, "Flow lookup"; #1481 C): raw flows for an incident, with a reason.
import i18next from 'i18next'
import { ApiError, get, post } from './client'

export const FLOW_LOOKUP_URL = '/api/traffic/lookup'
export const WINDOWS = ['15m', '1h', '6h', '24h', '7d'] as const
export type FlowWindow = (typeof WINDOWS)[number]

export interface FlowQuery {
  seat?: string
  source?: string
  /** An address, a network or an AS number ("AS64496"). */
  destination?: string
  ports?: string
  window: FlowWindow
  reason: string
}

export interface FlowRow {
  t: number
  src: string
  dst: string
  src_seat: string | null
  dst_seat: string | null
  protocol: string
  sport: number
  dport: number
  bytes: number
  packets: number
  owner: { asn: number; name: string } | null
  application?: string | null
  agent: string
}

export interface FlowAgent { name: string; total: number | null; error: string | null; oldest: string | null; stopped: boolean }

export interface FlowLookupAnswer {
  rows: FlowRow[]
  total: number
  bytes: number
  peers: number | null
  stopped: boolean
  agents: FlowAgent[]
  since: number
  until: number
}

export const searchFlows = (q: FlowQuery) => post<FlowLookupAnswer>(FLOW_LOOKUP_URL, q)

/** The same search as a CSV file: the server writes "Exported a flow lookup" to the audit log. */
export async function downloadFlows(q: FlowQuery): Promise<void> {
  const res = await fetch(FLOW_LOOKUP_URL, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'Accept-Language': i18next.language || 'en' },
    body: JSON.stringify({ ...q, csv: true }),
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>
    throw new ApiError(typeof data.error === 'string' ? data.error : `HTTP ${res.status}`, res.status, data)
  }
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? 'floorbit-flows.csv'
  a.click()
  URL.revokeObjectURL(url)
}

// The seat panel's traffic (#1481 B): a seat's top applications and networks' owners, 24 hours.
export interface SeatTrafficAnswer {
  seat: string
  hours: number
  bytes: number
  categories: Record<string, number>
  applications: { name: string; category: string; bytes: number }[]
  owners: { asn: number; name: string; bytes: number }[]
  stopped: boolean
  agents: { name: string; error: string | null }[]
}

export const seatTrafficUrl = (seat: string) => `/api/traffic/seat/${encodeURIComponent(seat)}`
export const fetchSeatTraffic = (seat: string) => get<SeatTrafficAnswer>(seatTrafficUrl(seat))
