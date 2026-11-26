import type { Permission } from './types'

// Roles and teams (auth/roles.py, auth/teams.py, auth/admin.py)
export interface RoleInfo {
  id: string
  label: string
  description: string
  permissions: Permission[]
  builtin: boolean
  users: number
}
export interface RolesList {
  permissions: { id: Permission; label: string }[]
  roles: RoleInfo[]
}
export interface TeamMember {
  username: string
  role: string
  role_label: string
}
export interface Team {
  id: string
  name: string
  parent: string | null
  depth: number
  members: TeamMember[]
}
export interface AccountSummary {
  username: string
  display_name: string
  role: string
}

/** An account on Settings > Users (auth/users.py ``public``): no secrets. */
export interface Account extends AccountSummary {
  role_label: string
  has_password: boolean
  /** Linked sign-ins: "discord" or "oidc:<provider>". */
  identities: string[]
  discord_id: string
  created_by: string | null
  /** The dashboards this account is limited to (a wall screen, #702); empty: every one. */
  dashboards: string[]
  /** Runs the platform: a flagged admin of the default tenant (docs/tenancy.md). */
  platform_admin?: boolean
}

export interface AccountsList {
  users: Account[]
  /** Whoever looks is a platform admin, so may give and take the flag. */
  platform?: boolean
  roles: { id: string; label: string; description: string }[]
  me: string | null
  discord: boolean
  oidc: { id: string; label: string }[]
}
export interface RoleMappingRule {
  value: string
  role: string
}
export interface OidcProvider {
  id: string
  name: string
  issuer: string
  client_id: string
  scopes: string
  role_claim: string
  role_mapping: RoleMappingRule[]
  secret_env: string
  secret_set: boolean
  callback_url: string
}
export interface OidcList {
  providers: OidcProvider[]
  roles: { id: string; label: string }[]
  callback_template: string
}
export interface OidcTestResult {
  ok: boolean
  error?: string
  problems?: string[]
  keys?: number
}

/** GET /api/auth/login-options: what the sign-in page offers (auth/__init__.py). */
export interface LoginOptions {
  enabled: boolean
  password_login: boolean
  providers: { id: string; label: string; url: string }[]
  no_users: boolean
  checkin_url: string | null
  /** The short address to type on a PC (CHECKIN_ADDRESS), e.g. checkin.lan. */
  checkin_address?: string | null
  next: string
  /** Why the last try failed (a wrong password, a provider that said no), shown once. */
  error: string | null
  username: string
}
