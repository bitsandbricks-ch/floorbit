// Every query key in one place, so two pages never share a key for different data.
export const qk = {
  me: ['me'] as const,
  dashboard: ['dashboard'] as const,
  widget: (url: string) => ['widget', url] as const,
  plugins: ['plugins'] as const,
  inventory: (hidden: boolean) => ['inventory', { hidden }] as const,
  inventoryAll: ['inventory'] as const,
  seatMap: ['seat-map'] as const,
  roles: ['roles'] as const,
  teams: ['teams'] as const,
  oidc: ['oidc'] as const,
  users: ['users'] as const,
  pluginLog: (id: string) => ['plugins', id, 'log'] as const,
}
