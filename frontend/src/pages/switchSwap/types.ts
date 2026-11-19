/** What /api/switch-swap/<id> answers (floorbit/switch_swap.py plan()). */
export type SwapSpare = { id: string; name: string; model: string; serial: string; same_model: boolean }
export type SwapEntry = {
  at: number; by: string; old_serial: string; old_model: string; new_serial: string; new_model: string; spare_id: string | null
}
export type SwapPlan = {
  switch: { id: string; name: string; model: string; serial: string; mgmt_ip: string; status: string; since: number | null }
  spares: SwapSpare[]
  config: { id: string; at: number | null } | null
  config_readable: boolean
  seat_ports: { port: string; seat: string }[]
  incident: { id: string; title: string } | null
  swaps: SwapEntry[]
}
