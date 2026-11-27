import type { Finding } from './security'
import type { TimelineEntry } from './timeline'

// Everything wrong right now, and muted switches (floorbit/problems.py).
export type ProblemKind = 'monitoring' | 'switch' | 'health' | 'security' | 'power' | 'link' | 'wifi' | 'plugin' | 'librenms'
  | 'flapping' | 'errors' | 'duplex' | 'checkin' | 'mapping' | 'log' | 'forecast'   // ports that need a look (issue #15)
  | 'incident'   // an open incident on a seat (issue #1204)
  | 'range'      // a seat outside its switch's IP range (issue #1062)
export interface AlertMute {
  /** The switch id, ``health:<service id>`` for a service (issue #256), ``wifi:<ap>`` for an access
   *  point, or ``problem:<problem id>`` for any other problem (issue #887). */
  switch_id: string
  kind?: 'switch' | 'health' | 'wifi' | 'problem'
  name: string
  until: number
  at: number
  by: string | null
  reason: string
}
export interface Problem {
  id: string
  kind: ProblemKind
  level: 'down' | 'warn'
  title: string
  where: string
  since: number | null
  link: string
  switch_id?: string
  /** The mute key: switches, services and Wi-Fi access points. */
  mute_id?: string
  name?: string
  muted?: { until: number; by: string | null; reason: string } | null
  /** An offline switch's open incident, for people who see the board (issue #278). */
  incident?: string | null
  /** The seat it is about: seat and port trouble, open incidents on a seat (issue #1204). */
  seat?: string | null
  /** What a down switch or link cuts off (issue #950): seat names only, and the switches behind it. */
  seats?: string[]
  behind?: string[]
  /** The down switch this one is behind: the place to start. */
  cause?: string
  /** A link's two boxes, so the page can hang it under one that is down (issue #1415). */
  ends?: string[]
  /** A LibreNMS alert: what DELETE /api/alerts/librenms/<id> takes when its recovery got lost (issue #951). */
  clear_id?: string
  ports?: string[]
  /** The switch it is on, when it is on one: what the page groups by (issue #883). */
  device?: string | null
  /** 1 down and cutting off more than itself, 2 down, 3 to look at; 1 too when raised by hand (issue #1364). */
  priority?: 1 | 2 | 3
  raised?: { by: string | null; at: number } | null
  /** The hall its switch or seat is in, and its switch's tags: what the page groups and filters by. */
  hall?: string | null
  tags?: string[]
}

/** GET /api/problems/<id> (issue #882): one problem, and the device it is on. */
export interface ProblemDetail {
  problem: Problem
  device: { id: string; name: string } | null
  can_mute: boolean
  can_report: boolean
  may_see_people: boolean
  /** A security finding's own details, for seats.view (issue #885). */
  finding?: Omit<Finding, 'title' | 'cleared_at'>
  can_shut?: boolean
  needs_login?: boolean
  /** The place's outages, incidents and alerts from the event changelog (issue #882). */
  history?: TimelineEntry[]
}
/** What to paste into LibreNMS's API transport (GET /api/alerts/librenms/setup). */
export interface LibreNMSAlertsSetup {
  enabled: boolean
  port: number
  method: string
  content_type: string
  body: string
  token: string
  active: number
  agents: { id: string; name: string; connected: boolean; url: string; address_known: boolean; status?: string | null; problem?: string }[]
}
export interface ProblemList {
  problems: Problem[]
  attention?: Problem[]
  /** `look` = warn + attention, `total` = down + look: the one count every place shows (#884). */
  counts: { down: number; warn: number; muted: number; attention?: number; seats?: number; look?: number; total?: number }
  mutes: AlertMute[]
  quiet_hours: boolean
  checked_at: number
  can_mute: boolean
  can_report?: boolean
}
