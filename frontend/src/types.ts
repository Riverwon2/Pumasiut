export interface HelpRequestInput {
  requesterName: string
  requestText: string
  date: string
  startTime: string
  endTime: string
}

export interface PlannedTask {
  taskId: string
  safetyFindingId: string
  title: string
  description: string
  date: string
  startTime: string | null
  endTime: string | null
  riskLevel: TaskRiskLevel
  scheduleSource?: 'ui_default' | 'natural_language' | 'user_confirmed'
  timeConstraintType?: 'window' | 'appointment' | 'deadline'
  targetTime?: string | null
  timeSourceText?: string | null
  scheduleNeedsConfirmation?: boolean
}

export type TaskRiskLevel = 'low' | 'mid'
export type SafetyClassification = TaskRiskLevel | 'high' | 'emergency' | 'not_actionable'

export interface SafetySummary {
  highestClassification: SafetyClassification
  emergencyBlocked: boolean
  highDiscardedCount: number
  notActionableCount: number
  midConfirmationCount: number
}

export interface HelperSummary {
  candidateId: string
  displayName: string
  distanceMeters: number
  completedHelpCount: number
}

export interface Assignment {
  task: PlannedTask
  helper: HelperSummary
  invitationMessage: string
}

export interface AssignmentPlan {
  requestSummary: string
  tasks: PlannedTask[]
  assignments: Assignment[]
  candidateQueues: TaskCandidateQueue[]
  unassignedTaskIds: string[]
  safety: SafetySummary
}

export interface CandidateOption {
  helper: HelperSummary
  invitationMessage: string
}

export interface TaskCandidateQueue {
  task: PlannedTask
  candidates: CandidateOption[]
}

export type StreamEvent =
  | { type: 'phase'; data: { message: string } }
  | { type: 'result'; data: AssignmentPlan }
  | { type: 'error'; data: { message: string } }

export type ResponseStatus = 'pending' | 'accepted' | 'declined'

export type TaskConnectionStatus =
  | 'waiting'
  | 'accepted'
  | 'completed'
  | 'unmatched'
  | 'confirmation_required'
  | 'schedule_required'
  | 'searching'

export type RequesterDemoStage =
  | 'form'
  | 'matching'
  | 'review_required'
  | 'matched'
  | 'partially_matched'
  | 'completed'
  | 'partially_completed'
  | 'unmatched'
  | 'emergency'
  | 'safety_excluded'
  | 'failed'
