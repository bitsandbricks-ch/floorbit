/** GET /api/speedtests/summary (issue #434): each seat's latest test, for the hall and per switch. */
export interface SpeedFigures { tests: number; down_mbps: number | null; up_mbps: number | null; ping_ms: number | null }
export interface SpeedSeat { seat: string; down_mbps: number | null; up_mbps: number | null; ping_ms: number | null; at: number }
export interface SpeedSwitch extends SpeedFigures { id: string; name: string; seats: SpeedSeat[]; slow: boolean }
export interface SpeedtestSummary { hours: number; hall: SpeedFigures; switches: SpeedSwitch[]; unknown: SpeedSeat[] }
