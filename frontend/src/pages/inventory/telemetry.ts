import { useQuery } from '@tanstack/react-query'
import { get } from '@/api/client'
import { qk } from '@/api/keys'

/** GET /api/telemetry/devices/<id> (floorbit/telemetry/targets.py for_device): no secrets. */
export interface DeviceTelemetryInfo {
  on: boolean
  platform: string
  logins: { snmp?: string; api?: string; trap?: string }
  /** What the device gets when nothing says otherwise: from its software, logins and interfaces. */
  auto: { drivers: string[]; fdb: string; vlans: number[]; mdt_node: string; address: string }
  /** What the collector does with it now; null while telemetry is off. */
  target: {
    drivers: string[]; fdb: string; vlans: number[]; mdt_node: string | null; address: string; agent: string
    /** Where it sends its traps on the agent (UDP); null: every listener belongs to another trap user. */
    trap_send_port?: number | null
    /** The SNMPv3 user its traps come as; absent for v2c. */
    trap_user?: string | null
  } | null
}

/** One device's telemetry for its Telemetry tab. */
export function useDeviceTelemetry(id: string) {
  return useQuery({ queryKey: qk.inventoryTelemetry(id), queryFn: () => get<DeviceTelemetryInfo>(`/api/telemetry/devices/${encodeURIComponent(id)}`) })
}

