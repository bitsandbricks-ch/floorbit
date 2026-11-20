import { useQuery } from '@tanstack/react-query'
import { get } from '@/api/client'
import { qk } from '@/api/keys'

// The telemetry device API (floorbit/blueprints/telemetry.py) for the components next to this file.

/** Why a device sends nothing, as the collector saw it (floorbit/telemetry/problems.py). */
export interface DeviceProblem { driver: string; kind: string; address: string; detail: string; since?: number; at?: number; count?: number; hint?: string; vlan?: number; table?: string }
/** What GET /api/telemetry/devices says about one device. */
export interface DeviceSeen { seen: number | null; online: boolean; ports?: number; macs?: number; arp?: number; neighbours?: number; problems?: DeviceProblem[] }

/** Every device's last word, fetched once for all components on the page (15 s). */
export function useTelemetryDevices() {
  return useQuery({ queryKey: qk.telemetryDevices, queryFn: () => get<{ devices: Record<string, DeviceSeen> }>('/api/telemetry/devices'), refetchInterval: 15_000 })
}

export interface TestResult {
  ok: boolean; name: string; agent: string; took_ms: number; points: number
  summary: { measurements: Record<string, number>; ports: number; sys_name: string | null }
  problems: DeviceProblem[]; notes: string[]; raw: string[]
}


/** One device's state as a page lists it: the agent's Devices tab (GET /api/agents/<id>/devices). */
export type DeviceState = 'silent' | 'never' | 'partial' | 'unknown' | 'waiting' | 'standby' | 'up'
export interface DeviceStateRow extends DeviceSeen {
  name: string; inventory_id: string | null; kind: string; platform: string; address: string; drivers: string[]
  state: DeviceState; pinned: boolean; collects?: boolean | null; pushed?: boolean
}
export interface AgentDevices {
  agent: { id: string; name: string }; connected: boolean; primary: boolean | null
  error: 'offline' | 'no_telemetry' | 'no_answer' | null; detail: string; devices: DeviceStateRow[]
}

/** What one agent collects (30 s). */
export function useAgentDevices(agentId: string) {
  return useQuery({ queryKey: [...qk.agents, agentId, 'devices'], queryFn: () => get<AgentDevices>(`/api/agents/${agentId}/devices`), refetchInterval: 30_000 })
}
