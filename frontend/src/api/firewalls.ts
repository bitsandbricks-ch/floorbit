export interface SeatFirewall { intended: string | null; now: string | null; state: FirewallRouteState; range: string; fallback?: string[] }
export type FirewallRouteState = 'primary' | 'failover' | 'unknown' | 'down'

/** GET /api/firewalls (issue #470): the firewalls with their health, and each seat range's route now. */
/** One firewall's equal share of a range (Mike, 2026-11-24): a range over four firewalls has four. */
export interface FirewallPart {
  cidr: string; firewall: string; now: string | null; state: FirewallRouteState; seats: number
}
export interface FirewallRange {
  id: string; cidr: string; name: string
  /** The firewalls the range is cut over, in order; ``fallback``: where a part goes while its own is down. */
  firewalls: string[]; fallback: string[]; parts: FirewallPart[]
  /** The worst of its parts. */
  state: FirewallRouteState; seats: number
  /** 'import': read from NetBox (change it there); 'floorbit': planned here. */
  source?: 'import' | 'floorbit'; plugin?: string
  /** Inventory switch or group ids the range is for: their seats outside it are flagged (issue #1062). */
  switches?: string[]
}
export interface FirewallCard {
  id: string; name: string; model: string; hall: string; status: 'online' | 'offline' | 'unknown'
  serving: string[]; planned: string[]; taken_over: string[]; seats: number
}
export interface FirewallList {
  firewalls: FirewallCard[]; ranges: FirewallRange[]; unread: boolean; monitoring?: boolean
  counts: { firewalls: number; down: number; failover: number; without: number }
}
