import { ThemeIcon } from '@mantine/core'
import {
  IconAccessPoint, IconAntenna, IconArrowsLeftRight, IconBatteryCharging, IconCamera, IconCloud, IconCpu, IconDatabase,
  IconDeviceDesktop, IconDeviceMobile, IconDevices, IconFlame, IconPlug, IconPrinter, IconRouter, IconServer, IconServer2,
  type Icon,
} from '@tabler/icons-react'

/** The icons a device, group or tag can show (floorbit/inventory.py ICONS). */
export const DEVICE_ICONS: Record<string, Icon> = {
  switch: IconArrowsLeftRight,
  router: IconRouter,
  firewall: IconFlame,
  server: IconServer,
  vm: IconServer2,
  'access-point': IconAccessPoint,
  pdu: IconPlug,
  ups: IconBatteryCharging,
  storage: IconDatabase,
  camera: IconCamera,
  printer: IconPrinter,
  screen: IconDeviceDesktop,
  phone: IconDeviceMobile,
  cloud: IconCloud,
  cpu: IconCpu,
  antenna: IconAntenna,
  other: IconDevices,
}


/** The icon in its colour (the device's own, else inherited, else the role's in the accent). */
export function DeviceIcon({ icon, color, size = 26 }: { icon: string; color?: string; size?: number }) {
  const Glyph = DEVICE_ICONS[icon] ?? IconDevices
  return (
    <ThemeIcon size={size} radius="md" variant={color ? 'filled' : 'light'} color={color || 'trace'} aria-hidden="true">
      <Glyph size={Math.round(size * 0.62)} />
    </ThemeIcon>
  )
}
