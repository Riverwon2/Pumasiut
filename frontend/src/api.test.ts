import { describe, expect, it } from 'vitest'

import { parseSseChunk } from './api'

describe('parseSseChunk', () => {
  it('keeps partial events until the next chunk arrives', () => {
    const first = parseSseChunk('event: phase\ndata: {"message":"확인 중')
    expect(first.events).toEqual([])

    const second = parseSseChunk(`${first.remainder}이에요."}\n\n`)
    expect(second.events).toEqual([
      { type: 'phase', data: { message: '확인 중이에요.' } },
    ])
  })

  it('parses a result event', () => {
    const result = parseSseChunk(
      'event: result\ndata: {"requestSummary":"요약","tasks":[],"assignments":[],"candidateQueues":[],"unassignedTaskIds":[]}\n\n',
    )
    expect(result.events[0]?.type).toBe('result')
  })

})
