import { describe, expect, it } from 'vitest'

import {
  applyConfirmedSchedule,
  deriveRequesterStage,
  initialTaskConnectionStatus,
} from './workflow'

const scheduledTask = {
  taskId: 'task-1',
  safetyFindingId: 'finding-1',
  title: '회사 이동 지원',
  description: '회사까지 이동을 지원합니다.',
  date: '2026-08-03',
  startTime: null,
  endTime: null,
  riskLevel: 'low' as const,
  scheduleSource: 'natural_language' as const,
  timeConstraintType: 'deadline' as const,
  targetTime: '10:00',
  timeSourceText: '10시까지 출근',
  scheduleNeedsConfirmation: true,
}

describe('task schedule confirmation', () => {
  it('holds an incomplete schedule before any safety or candidate state', () => {
    expect(initialTaskConnectionStatus(scheduledTask, 2)).toBe('schedule_required')
  })

  it('uses only the requester-confirmed interval for matching', () => {
    expect(applyConfirmedSchedule(scheduledTask, '09:20', '10:00')).toEqual(
      expect.objectContaining({
        startTime: '09:20',
        endTime: '10:00',
        scheduleSource: 'user_confirmed',
        scheduleNeedsConfirmation: false,
      }),
    )
  })

  it('does not invent or accept an incomplete interval', () => {
    expect(() => applyConfirmedSchedule(scheduledTask, '', '10:00')).toThrow()
  })
})

describe('deriveRequesterStage', () => {
  it('pauses matching while a safety confirmation is required', () => {
    expect(deriveRequesterStage(['confirmation_required'])).toBe('review_required')
    expect(deriveRequesterStage(['searching', 'accepted'])).toBe('review_required')
  })

  it('pauses matching while an incomplete task time is being confirmed', () => {
    expect(deriveRequesterStage(['schedule_required', 'accepted'])).toBe('review_required')
  })

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
