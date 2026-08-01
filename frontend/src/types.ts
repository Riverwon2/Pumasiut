export interface HelpRequestInput {
  requesterName: string
  requestText: string
  date: string
  startTime: string
  endTime: string
}

export interface PlannedTask {
  taskId: string
  title: string
  description: string
  date: string
  startTime: string
  endTime: string
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

export type TaskConnectionStatus = 'waiting' | 'accepted' | 'completed' | 'unmatched'

export type RequesterDemoStage =
  | 'form'
  | 'matching'
  | 'matched'
  | 'partially_matched'
  | 'completed'
  | 'partially_completed'
  | 'unmatched'
  | 'failed'
