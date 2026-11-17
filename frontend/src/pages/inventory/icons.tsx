import { ThemeIcon } from '@mantine/core'
import {
  IconAccessPoint, IconAntenna, IconArrowsLeftRight, IconBatteryCharging, IconCamera, IconCloud, IconCpu, IconDatabase,
  IconBoxMultiple, IconBuildingWarehouse, IconCircuitSwitchClosed, IconCube, IconDeviceDesktop, IconDeviceMobile, IconDevices,
  IconFlame, IconLayoutRows, IconNetwork, IconPlug, IconPlugConnected, IconPrinter, IconRouter, IconServer, IconServer2,
  type Icon,
} from '@tabler/icons-react'
import { useCustomIcons } from './scope'

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
  cable: IconPlugConnected,
  circuit: IconCircuitSwitchClosed,
  'power-board': IconBoxMultiple,
  'patch-panel': IconLayoutRows,
  rack: IconBuildingWarehouse,
  transceiver: IconCube,
  vlan: IconNetwork,
  other: IconDevices,
}

/** An uploaded icon in the text colour around it. Drawn as a CSS mask, so the SVG is only ever
 *  an image: nothing in it can run, even if the server's cleaning missed something. */
export function CustomIconGlyph({ url, size, label }: { url: string; size: number; label?: string }) {
  const mask = `url("${url}") center / contain no-repeat`
  return (
    <span role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}
      style={{ display: 'inline-block', width: size, height: size, backgroundColor: 'currentColor', mask, WebkitMask: mask }} />
  )
}

/** The icon in its colour (the device's own, else inherited, else the role's in the accent).
 *  `icon` is a built-in name or an uploaded icon's id; one that is gone shows the generic device. */
export function DeviceIcon({ icon, color, size = 26 }: { icon: string; color?: string; size?: number }) {
  const custom = icon.startsWith('custom-')
  const { data } = useCustomIcons(custom)
  const uploaded = custom ? data?.icons.find((i) => i.id === icon) : undefined
  const Glyph = DEVICE_ICONS[icon] ?? IconDevices
  const inner = Math.round(size * 0.62)
  return (
    <ThemeIcon size={size} radius="md" variant={color ? 'filled' : 'light'} color={color || 'trace'} aria-hidden="true">
      {uploaded ? <CustomIconGlyph url={uploaded.url} size={inner} /> : <Glyph size={inner} />}
    </ThemeIcon>
  )
}
