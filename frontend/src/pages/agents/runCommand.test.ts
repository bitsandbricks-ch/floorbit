import { describe, expect, it } from 'vitest'
import { runCommand } from './runCommand'

const made = { name: 'Hall B', key: 'fba_example', image: 'ghcr.io/bitsandbricks-ch/floorbit-agent:0123456789ab' }

describe('runCommand', () => {
  it('pins the image, keeps the state and publishes what is on by default', () => {
    const run = runCommand(made, 'https://floor.example.com')
    expect(run).toContain('-e FLOORBIT_URL=https://floor.example.com')
    expect(run).toContain('-e FLOORBIT_AGENT_KEY=fba_example')
    expect(run).toContain('-v floorbit-agent:/app/state')
    expect(run).toContain('-p 443:8443 -p 80:8080')
    expect(run.trim().endsWith(':0123456789ab')).toBe(true)
    expect(run).not.toContain('INSECURE')
  })

  it('lets the agent talk to a plain http Floorbit', () => {
    expect(runCommand(made, 'http://192.0.2.10:5000')).toContain('-e FLOORBIT_AGENT_INSECURE=1')
  })

  it('falls back to latest without an image from the server', () => {
    expect(runCommand({ name: 'x', key: 'k' }, 'https://floor.example.com')).toMatch(/floorbit-agent:latest$/)
  })
})
