import { notifications } from '@mantine/notifications'

// Feedback after an action (#1021): a toast at the bottom that goes away by itself, so the page
// doesn't shift. Inline Alerts are for states that stay (an agent offline, a secret shown once).

/** "Saved", "Test sent", "3 items imported". */
export function toastDone(message: string) {
  notifications.show({ color: 'up', message, autoClose: 4000 })
}

/** An action that failed, with the server's words. Failures of a form stay next to the form. */
export function toastFailed(error: unknown) {
  notifications.show({ color: 'down', message: error instanceof Error ? error.message : String(error), autoClose: 8000 })
}
