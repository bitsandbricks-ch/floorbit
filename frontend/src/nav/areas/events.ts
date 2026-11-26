import { IconCalendar, IconCalendarEvent, IconHistory, IconPlayerPlay, IconReport, IconTemplate } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Events: schedule, timeline, replay, report and templates as tabs.
export const area: NavArea = {
  hub: 'events',
  tabs: ['schedule', 'timeline', 'replay', 'report', 'templates'],
  icons: {
    events: IconCalendarEvent,
    schedule: IconCalendar,
    timeline: IconHistory,
    replay: IconPlayerPlay,
    report: IconReport,
    templates: IconTemplate,
    event: IconCalendarEvent,
  },
}
