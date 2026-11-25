// Outgoing webhooks (floorbit/webhooks.py)
export interface WebhookDelivery {
  at: number
  event: string
  delivery: string
  ok: boolean
  status: number | null
  error: string | null
  attempt: number
}
export interface Webhook {
  id: string
  name: string
  url: string
  events: string[]
  active: boolean
  created_at: number
  created_by: string | null
  last: WebhookDelivery | null
  deliveries: WebhookDelivery[]
}
