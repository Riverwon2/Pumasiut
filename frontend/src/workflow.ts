import type { RequesterDemoStage, TaskConnectionStatus } from './types'

export function deriveRequesterStage(
  states: readonly TaskConnectionStatus[],
): RequesterDemoStage {
  if (states.some((state) => state === 'confirmation_required' || state === 'searching')) {
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
