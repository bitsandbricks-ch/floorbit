export interface ApiToken {
  id: string
  name: string
  role: string
  role_label: string
  read_only: boolean
  created_at: number
  created_by: string | null
  expires_at: number | null
  expired: boolean
  last_used_at: number | null
}
