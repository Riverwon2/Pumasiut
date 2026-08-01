import { afterEach, describe, expect, it, vi } from 'vitest'

import { matchConfirmedTask, parseSseChunk } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

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
      'event: result\ndata: {"requestSummary":"요약","tasks":[],"assignments":[],"candidateQueues":[],"unassignedTaskIds":[],"safety":{"highestClassification":"low","emergencyBlocked":false,"highDiscardedCount":0,"notActionableCount":0,"midConfirmationCount":0}}\n\n',
    )
    expect(result.events[0]?.type).toBe('result')
  })

  it('keeps legacy result events without safety data from blanking the UI', () => {
    const result = parseSseChunk(
      'event: result\ndata: {"requestSummary":"요약","tasks":[],"assignments":[],"candidateQueues":[],"unassignedTaskIds":[]}\n\n',
    )

    expect(result.events[0]).toEqual(expect.objectContaining({
      type: 'result',
      data: expect.objectContaining({
        safety: expect.objectContaining({ emergencyBlocked: false }),
      }),
    }))
  })

  it('searches a confirmed mid task with existing candidates excluded', async () => {
    const task = {
      taskId: 'task-2',
      safetyFindingId: 'finding-2',
      title: '아이 학교 등교 동행',
      description: '아이를 학교까지 데려다줍니다.',
      date: '2026-08-03',
      startTime: '08:00',
      endTime: '09:00',
      riskLevel: 'mid' as const,
    }
    const queue = { task, candidates: [] }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => queue })
    vi.stubGlobal('fetch', fetchMock)

    await expect(matchConfirmedTask('김하늘', task, ['helper-1'])).resolves.toEqual(queue)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/tasks/confirm-match',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          requesterName: '김하늘',
          task,
          excludedCandidateIds: ['helper-1'],
        }),
      }),
    )
  })
})
