import type { ReactNode } from 'react'
import { Box, Group, Stack, Text, Title } from '@mantine/core'

// From Hubra (by Mike): packages/ui/src/layout.tsx.
export function PageHead({ title, desc, actions }: { title: ReactNode; desc?: ReactNode; actions?: ReactNode }) {
  return (
    <Box mb={24}>
      <Group justify="space-between" align="flex-end" gap={16} wrap="wrap">
        <Stack gap={6} style={{ minWidth: 0, flex: '1 1 320px' }}>
          <Title order={2} style={{ margin: 0, overflowWrap: 'anywhere' }}>
            {title}
          </Title>
          {desc && (
            <Text size="md" c="dimmed" maw={720}>
              {desc}
            </Text>
          )}
        </Stack>
        {actions && (
          <Group gap="xs" wrap="wrap" align="center">
            {actions}
          </Group>
        )}
      </Group>
    </Box>
  )
}
