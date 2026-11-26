/** One row of the IP and MAC history (floorbit/endpoints.py): a machine seen on a port. */
export interface EndpointRow {
  mac: string
  ip: string | null
  device: string
  port: string | null
  seat: string | null
  vlan: number | null
  first_seen: number
  last_seen: number
}

export interface EndpointAnswer {
  rows: EndpointRow[]
  status: { store: 'database'; written: number; open: number; keep_days: number; error: string | null }
}
