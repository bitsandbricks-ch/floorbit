import { fireEvent, screen } from '@testing-library/react'

const opts = (values: string[], used: Record<string, string> = {}) =>
  ({ options: values.map((v) => ({ value: v, label: v, ...(used[v] ? { used: used[v] } : {}) })) })

/** What GET /api/options/<kind> answers in page tests: a few switches, a 48-port switch, seats. */
export const OPTIONS = {
  'GET /api/options/switches': opts(['sw-a-01', 'sw-b-02']),
  'GET /api/options/ports?switch=sw-a-01': opts(Array.from({ length: 48 }, (_, n) => `Gi1/0/${n + 1}`), { 'Gi1/0/3': 'A-3' }),
  'GET /api/options/ports?switch=sw-b-02': opts(Array.from({ length: 24 }, (_, n) => `Gi1/0/${n + 1}`), { 'Gi1/0/12': 'B-14' }),
  'GET /api/options/seats': opts([...Array.from({ length: 16 }, (_, n) => `A-${n + 1}`), 'B-9', 'B-14', 'D-6', 'D-7', 'D-8']),
}

/** Pick ``option`` in the select labelled ``label`` (EntitySelect or Select), like a person would. */
export async function pick(label: string, option: string) {
  const box = await screen.findByRole('combobox', { name: label })
  fireEvent.click(box)
  fireEvent.click(await screen.findByRole('option', { name: option, hidden: true }))
}
