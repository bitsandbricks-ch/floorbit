/** Game servers (issue #472): their last answer, and whether RCON is set up. Never the password. */
export interface GameServerInfo {
  name: string; map: string; game: string; version: string
  players: number; max_players: number; bots: number; ping_ms: number | null
}
export interface GameServer {
  id: string; name: string; game: string; host: string; port: number; query: 'a2s' | 'minecraft' | 'tcp'
  rcon_port: number | null; rcon: boolean
  /** The inventory server or VM it runs on, or ''. */
  runs_on?: string
  status: 'up' | 'down' | 'unknown'; info: GameServerInfo | null; error: string
  checked_at: number | null; since: number | null
  /** [when, players] oldest first; players is null while it was down. */
  history: [number, number | null][]
}
export interface GameServerList {
  servers: GameServer[]; interval: number; last_poll: number | null; via_agent: boolean
  counts: { up: number; down: number; unknown: number }; players: number
}
export interface RconAnswer { server: string; command: string; answer: string }
