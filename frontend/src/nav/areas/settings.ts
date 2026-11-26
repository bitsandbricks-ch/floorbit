import { IconBuildingCommunity, IconKey, IconLayoutSidebar, IconLogin, IconPuzzle, IconSettings, IconToggleRight, IconUsers, IconUsersGroup, IconWebhook } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Settings: draws its tabs itself (pages/Settings.tsx).
export const area: NavArea = {
  hub: 'settings',
  tabs: ['plugins', 'users', 'teams', 'signIn', 'apiTokens', 'webhooks', 'tenants', 'sidebarSections'],
  icons: {
    settings: IconSettings,
    plugins: IconPuzzle,
    users: IconUsers,
    teams: IconUsersGroup,
    signIn: IconLogin,
    apiTokens: IconKey,
    webhooks: IconWebhook,
    tenants: IconBuildingCommunity,
    sidebarSections: IconLayoutSidebar,
    features: IconToggleRight,
  },
}
