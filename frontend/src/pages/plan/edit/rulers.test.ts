import { describe, expect, it } from 'vitest'
import { rulerSteps } from './rulers'

describe('ruler numbers', () => {
  it('numbers fewer seats the further out the view is', () => {
    expect(rulerSteps(64)).toEqual({ major: 1, minor: 1 })
    expect(rulerSteps(32)).toEqual({ major: 2, minor: 1 })
    expect(rulerSteps(8)).toEqual({ major: 10, minor: 1 })
    expect(rulerSteps(2)).toEqual({ major: 50, minor: 5 })
  })
})
