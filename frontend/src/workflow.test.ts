import { describe, expect, it } from 'vitest'

import { deriveRequesterStage } from './workflow'

describe('deriveRequesterStage', () => {
  it('keeps an accepted request distinct from a completed request', () => {
    expect(deriveRequesterStage(['accepted'])).toBe('matched')
    expect(deriveRequesterStage(['completed'])).toBe('completed')
  })

  it('waits for every connected request to be completed', () => {
    expect(deriveRequesterStage(['completed', 'accepted'])).toBe('matched')
    expect(deriveRequesterStage(['completed', 'completed'])).toBe('completed')
  })

  it('reports completion separately when only part of the request was matched', () => {
    expect(deriveRequesterStage(['accepted', 'unmatched'])).toBe('partially_matched')
    expect(deriveRequesterStage(['completed', 'unmatched'])).toBe('partially_completed')
  })
})
