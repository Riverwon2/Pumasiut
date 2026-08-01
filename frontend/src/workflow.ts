import type { PlannedTask, RequesterDemoStage, TaskConnectionStatus } from './types'

export function initialTaskConnectionStatus(
  task: PlannedTask,
  candidateCount: number,
): TaskConnectionStatus {
  if (task.scheduleNeedsConfirmation) return 'schedule_required'
  if (task.riskLevel === 'mid') return 'confirmation_required'
  return candidateCount > 0 ? 'waiting' : 'unmatched'
}

export function applyConfirmedSchedule(
  task: PlannedTask,
  startTime: string,
  endTime: string,
): PlannedTask {
  if (!startTime || !endTime || startTime >= endTime) {
    throw new Error('작업 종료 시간은 시작 시간보다 늦어야 합니다.')
  }
  return {
    ...task,
    startTime,
    endTime,
    scheduleSource: 'user_confirmed',
    scheduleNeedsConfirmation: false,
  }
}

export function deriveRequesterStage(
  states: readonly TaskConnectionStatus[],
): RequesterDemoStage {
  if (states.some((state) =>
    ['confirmation_required', 'schedule_required', 'searching'].includes(state),
  )) {
    return 'review_required'
  }
  if (states.some((state) => state === 'waiting')) return 'matching'

  const accepted = states.filter((state) => state === 'accepted').length
  const completed = states.filter((state) => state === 'completed').length
  const connected = accepted + completed

  if (completed === states.length && completed > 0) return 'completed'
  if (accepted === 0 && completed > 0) return 'partially_completed'
  if (connected === states.length && connected > 0) return 'matched'
  if (connected > 0) return 'partially_matched'
  return 'unmatched'
}
