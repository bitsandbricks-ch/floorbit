import type { Made } from './KeyAlert'

/** The line that starts the agent: pinned image, its state kept in a volume, and the ports of what
 * is on by default (attendees on 443 and 80, SNMP traps, Cisco telemetry), like docker-compose.agent.yml. */
export function runCommand(made: Made, origin: string) {
  const insecure = origin.startsWith('http://')
  return [
    'docker run -d --restart on-failure:3 --name floorbit-agent \\',
    `  -e FLOORBIT_URL=${origin} \\`,
    `  -e FLOORBIT_AGENT_KEY=${made.key} \\`,
    ...(insecure ? ['  -e FLOORBIT_AGENT_INSECURE=1 \\'] : []),
    '  -v floorbit-agent:/app/state \\',
    '  -p 443:8443 -p 80:8080 -p 162:1162/udp -p 57000:57000 \\',
    `  ${made.image ?? 'ghcr.io/bitsandbricks-ch/floorbit-agent:latest'}`,
  ].join('\n')
}
