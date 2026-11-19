import { useQuery } from '@tanstack/react-query'
import { get } from '@/api/client'
import { qk } from '@/api/keys'

// The telemetry device API (floorbit/blueprints/telemetry.py) for the components next to this file.

/** Why a device sends nothing, as the collector saw it (floorbit/telemetry/problems.py). */
export interface DeviceProblem { driver: string; kind: string; address: string; detail: string; since?: number; at?: number; count?: number; hint?: string }
/** What GET /api/settings/telemetry/devices says about one device. */
export interface DeviceSeen { seen: number | null; online: boolean; ports?: number; macs?: number; arp?: number; neighbours?: number; problems?: DeviceProblem[] }

/** Every device's last word, fetched once for all components on the page (15 s). */
export function useTelemetryDevices() {
  return useQuery({ queryKey: qk.telemetryDevices, queryFn: () => get<{ devices: Record<string, DeviceSeen> }>('/api/settings/telemetry/devices'), refetchInterval: 15_000 })
}

export interface TestResult {
  ok: boolean; name: string; agent: string; took_ms: number; points: number
  summary: { measurements: Record<string, number>; ports: number; sys_name: string | null }
  problems: DeviceProblem[]; notes: string[]; raw: string[]
}

