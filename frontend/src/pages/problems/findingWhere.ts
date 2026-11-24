/** Where a finding is: its seat and port, or the port alone. */
export function findingWhere(f: { switch: string; port: string; seat?: string | null }, t: (k: string, o?: Record<string, unknown>) => string) {
  const port = [f.switch, f.port].filter(Boolean).join(' · ')
  return f.seat ? `${t('security.seat', { seat: f.seat })} (${port})` : port
}
