import { describe, expect, it } from 'vitest'
import { filterlogText, parseFilterlog } from './filterlog'

describe('filterlog (issue #1429)', () => {
  it('reads an IPv4 UDP line', () => {
    const p = parseFilterlog('5,,,1000000103,igb1,match,block,in,4,0x0,,64,1234,0,none,17,udp,76,203.0.113.9,198.51.100.1,123,123,56')
    expect(p && filterlogText(p)).toBe('block in · igb1 · UDP 203.0.113.9:123 → 198.51.100.1:123')
  })

  it('reads an IPv4 TCP line with its flags after the ports', () => {
    const p = parseFilterlog('9,,,1000000104,em0,match,pass,out,4,0x0,,63,0,0,DF,6,tcp,60,192.0.2.5,198.51.100.7,51000,443,0,S,1,,64240,,mss')
    expect(p && filterlogText(p)).toBe('pass out · em0 · TCP 192.0.2.5:51000 → 198.51.100.7:443')
  })

  it('reads an IPv6 line, ports in brackets', () => {
    const p = parseFilterlog('7,,,1000000105,igb0,match,block,in,6,0x00,0x00000,255,udp,17,40,2001:db8::1,2001:db8::2,5353,5353,40')
    expect(p && filterlogText(p)).toBe('block in · igb0 · UDP [2001:db8::1]:5353 → [2001:db8::2]:5353')
  })

  it('leaves the ports out for ICMP', () => {
    const p = parseFilterlog('5,,,1000000103,igb1,match,block,in,4,0x0,,64,1,0,none,1,icmp,84,203.0.113.9,198.51.100.1,request,1,2')
    expect(p && filterlogText(p)).toBe('block in · igb1 · ICMP 203.0.113.9 → 198.51.100.1')
  })

  it('says no to anything else', () => {
    expect(parseFilterlog('Interface GigabitEthernet1/0/1, changed state to down')).toBeNull()
    expect(parseFilterlog('5,,,1,igb1,match,block,in,9,a,b')).toBeNull()
  })
})
