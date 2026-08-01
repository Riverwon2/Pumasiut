import { type FormEvent, useMemo, useRef, useState } from 'react'

import { streamHelpRequest } from './api'
import type {
  Assignment,
  AssignmentPlan,
  HelpRequestInput,
  RequesterDemoStage,
  ResponseStatus,
  StreamEvent,
  TaskCandidateQueue,
  TaskConnectionStatus,
} from './types'
import { deriveRequesterStage } from './workflow'

const SAMPLE_REQUEST =
  '시각장애인인데 안내견이 아파요. 강아지를 동물병원에 데려다주고, 저의 출근 준비를 도와줄 사람이 필요해요.'

const orbitHeartPositions = [
  'top',
  'top-right',
  'right',
  'bottom-right',
  'bottom',
  'bottom-left',
  'left',
  'top-left',
] as const

interface TaskConnection {
  candidateIndex: number
  status: TaskConnectionStatus
  retried: boolean
}

type HelperCardStatus = 'pending' | 'accepted' | 'completed'
type HelperDecision = Exclude<ResponseStatus, 'pending'>

interface FormErrors {
  requesterName?: string
  requestText?: string
  date?: string
  time?: string
}

function tomorrow(): string {
  const value = new Date()
  value.setDate(value.getDate() + 1)
  return value.toLocaleDateString('sv-SE')
}

function formatDate(date: string): string {
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  }).format(new Date(`${date}T00:00:00`))
}

function formatDistance(meters: number): string {
  if (meters < 1000) return `${meters.toLocaleString()}m`
  return `${(meters / 1000).toFixed(1)}km`
}

function validate(input: HelpRequestInput): FormErrors {
  const errors: FormErrors = {}
  if (!input.requesterName.trim()) errors.requesterName = '요청자 이름을 입력해주세요.'
  if (input.requestText.trim().length < 5) {
    errors.requestText = '도움이 필요한 내용을 입력해주세요.'
  }
  if (!input.date) errors.date = '날짜를 선택해주세요.'
  if (!input.startTime || !input.endTime || input.startTime >= input.endTime) {
    errors.time = '종료 시간은 시작 시간보다 늦어야 합니다.'
  }
  return errors
}

function CareFace({ stage }: { readonly stage: RequesterDemoStage }) {
  const settled = ['matched', 'partially_matched', 'completed', 'partially_completed'].includes(stage)
  const stopped = ['unmatched', 'failed'].includes(stage)

  return (
    <div
      className={`care-face-wrap ${settled ? 'care-face-wrap--settled' : ''} ${stopped ? 'care-face-wrap--stopped' : ''}`}
      aria-hidden="true"
    >
      {orbitHeartPositions.map((position) => (
        <span className={`orbit-heart orbit-heart--${position}`} key={position}>
          ♥
        </span>
      ))}
      <svg className="care-face" viewBox="0 0 180 180">
        <circle cx="90" cy="90" r="70" />
        <path className="care-eye" d="M52 78c7-12 18-12 25 0" />
        <path className="care-eye" d="M103 78c7-12 18-12 25 0" />
        <path className="care-smile" d="M55 105c17 28 53 28 70 0" />
      </svg>
    </div>
  )
}

function AgentConsole({
  logs,
  isLoading,
  completed,
  errorMessage,
}: {
  logs: string[]
  isLoading: boolean
  completed: boolean
  errorMessage: string
}) {
  return (
    <section className="agent-console" aria-labelledby="agent-heading" aria-live="polite">
      <div className="console-heading">
        <div>
          <span className={`agent-orb ${isLoading ? 'agent-orb--active' : ''}`} aria-hidden="true" />
          <h2 id="agent-heading">에이전트 처리 현황</h2>
        </div>
        <span>{isLoading ? '처리 중' : completed ? '완료' : '대기 중'}</span>
      </div>

      {logs.length === 0 && !errorMessage ? (
        <p className="console-empty">에이전트가 작업과 도우미 연결 상태를 확인하고 있어요.</p>
      ) : (
        <ol className="console-log">
          {logs.map((log, index) => (
            <li key={`${log}-${index}`} className={index === logs.length - 1 ? 'is-current' : ''}>
              <span>{index < logs.length - 1 || completed ? '✓' : index + 1}</span>
              {log}
            </li>
          ))}
        </ol>
      )}
      {errorMessage && <p className="console-error" role="alert">{errorMessage}</p>}
    </section>
  )
}

function connectionCopy(queue: TaskCandidateQueue, connection: TaskConnection | undefined) {
  if (!connection || connection.status === 'waiting') {
    const candidate = queue.candidates[connection?.candidateIndex ?? 0]
    return {
      title: candidate ? `${candidate.helper.displayName}님 연결 중` : '도우미 연결 중',
      badge: connection?.retried ? '다음 후보 대기' : '응답 대기',
      tone: 'waiting',
    }
  }
  if (connection.status === 'accepted') {
    const candidate = queue.candidates[connection.candidateIndex]
    return {
      title: candidate ? `${candidate.helper.displayName}님이 요청을 수락했어요` : '요청을 수락했어요',
      badge: '수락 완료',
      tone: 'accepted',
    }
  }
  if (connection.status === 'completed') {
    const candidate = queue.candidates[connection.candidateIndex]
    return {
      title: candidate ? `${candidate.helper.displayName}님이 요청을 완료했어요` : '요청이 완료되었어요',
      badge: '요청 완료',
      tone: 'completed',
    }
  }
  return { title: '연결 가능한 지원자 없음', badge: '지원자 없음', tone: 'unmatched' }
}

function HelperCard({
  assignment,
  status,
  attempt,
  onRespond,
  onRequestComplete,
}: {
  assignment: Assignment
  status: HelperCardStatus
  attempt: number
  onRespond: (status: HelperDecision) => void
  onRequestComplete: () => void
}) {
  if (status === 'completed') {
    return (
      <article
        className="helper-card helper-card--completed"
        role="status"
        aria-label={`${assignment.task.title} 요청 완료`}
      >
        <span className="completion-thanks__icon" aria-hidden="true">♥</span>
        <p>따뜻한 세상을 위해 노력해주셔서 감사합니다.</p>
      </article>
    )
  }

  return (
    <article className={`helper-card helper-card--${status}`}>
      <div className="helper-card__topline">
        <span className="helper-avatar" aria-hidden="true">
          {assignment.helper.displayName.slice(-2)}
        </span>
        <div>
          <p className="eyebrow">도움 요청 도착 · 후보 {attempt}/2</p>
          <h3>{assignment.helper.displayName}</h3>
        </div>
        <span className="distance-pill">{formatDistance(assignment.helper.distanceMeters)}</span>
      </div>

      <div className="request-bubble">
        <span className="bubble-mark" aria-hidden="true">“</span>
        <p>
          {status === 'accepted'
            ? '요청 수행 후 아래의 요청 완료 버튼을 눌러주세요!'
            : assignment.invitationMessage}
        </p>
      </div>

      <div className="task-detail">
        <span className="task-number">{assignment.task.taskId.replace('task-', '')}</span>
        <div>
          <h4>{assignment.task.title}</h4>
          <p>{assignment.task.description}</p>
        </div>
      </div>

      <dl className="helper-meta">
        <div><dt>일정</dt><dd>{formatDate(assignment.task.date)}</dd></div>
        <div><dt>시간</dt><dd>{assignment.task.startTime}–{assignment.task.endTime}</dd></div>
        <div><dt>도움 경험</dt><dd>{assignment.helper.completedHelpCount}회</dd></div>
      </dl>

      {status === 'accepted' ? (
        <div className="request-complete-action">
          <button
            type="button"
            className="request-complete-button"
            onClick={onRequestComplete}
          >
            요청 완료
          </button>
        </div>
      ) : (
        <div className="response-actions">
          <button type="button" className="button button--decline" onClick={() => onRespond('declined')}>
            거부
          </button>
          <button type="button" className="button button--accept" onClick={() => onRespond('accepted')}>
            수락
          </button>
        </div>
      )}
    </article>
  )
}

export default function App() {
  const [form, setForm] = useState<HelpRequestInput>({
    requesterName: '김하늘',
    requestText: SAMPLE_REQUEST,
    date: tomorrow(),
    startTime: '08:00',
    endTime: '09:00',
  })
  const [errors, setErrors] = useState<FormErrors>({})
  const [logs, setLogs] = useState<string[]>([])
  const [plan, setPlan] = useState<AssignmentPlan | null>(null)
  const [connections, setConnections] = useState<Record<string, TaskConnection>>({})
  const [stage, setStage] = useState<RequesterDemoStage>('form')
  const [errorMessage, setErrorMessage] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  const isLoading = stage === 'matching' && !plan
  const isTerminal = ['completed', 'partially_completed', 'unmatched', 'failed'].includes(stage)
  const isSuccessfulMatchingComplete = stage === 'matched' || stage === 'completed'
  const agentCompleted = stage === 'failed' || (
    plan !== null && Object.values(connections).every(({ status }) => status !== 'waiting')
  )

  const activeAssignments = useMemo(() => {
    if (!plan) return []
    return plan.candidateQueues.flatMap((queue) => {
      const connection = connections[queue.task.taskId]
      if (!connection || connection.status === 'unmatched') return []
      const option = queue.candidates[connection.candidateIndex]
      if (!option) return []
      return [{
        assignment: {
          task: queue.task,
          helper: option.helper,
          invitationMessage: option.invitationMessage,
        },
        connection,
      }]
    })
  }, [connections, plan])

  const allRequestsCompleted = activeAssignments.length > 0
    && activeAssignments.every(({ connection }) => connection.status === 'completed')

  const updateForm = (field: keyof HelpRequestInput, value: string) => {
    setForm((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: undefined, time: undefined }))
  }

  const appendLog = (message: string) => {
    setLogs((current) => current.includes(message) ? current : [...current, message])
  }

  const stageFromConnections = (
    candidatePlan: AssignmentPlan,
    nextConnections: Record<string, TaskConnection>,
  ): RequesterDemoStage => {
    const states = candidatePlan.candidateQueues.map(
      (queue) => nextConnections[queue.task.taskId]?.status ?? 'unmatched',
    )
    return deriveRequesterStage(states)
  }

  const handleEvent = (event: StreamEvent) => {
    if (event.type === 'phase') {
      appendLog(event.data.message)
      return
    }
    if (event.type === 'result') {
      setPlan(event.data)
      const initialConnections = Object.fromEntries(
        event.data.candidateQueues.map((queue) => [
          queue.task.taskId,
          {
            candidateIndex: 0,
            status: queue.candidates.length > 0 ? 'waiting' : 'unmatched',
            retried: false,
          } satisfies TaskConnection,
        ]),
      )
      setConnections(initialConnections)
      setStage(stageFromConnections(event.data, initialConnections))
      return
    }
    setErrorMessage(event.data.message)
    setStage('failed')
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const validationErrors = validate(form)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) return

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setStage('matching')
    setErrorMessage('')
    setPlan(null)
    setLogs([])
    setConnections({})

    try {
      await streamHelpRequest(form, handleEvent, controller.signal)
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        setErrorMessage((error as Error).message)
        setStage('failed')
      }
    }
  }

  const handleHelperResponse = (
    taskId: string,
    response: HelperDecision,
  ) => {
    if (!plan) return
    const queue = plan.candidateQueues.find((item) => item.task.taskId === taskId)
    if (!queue) return

    setConnections((current) => {
      const existing = current[taskId]
      if (!existing || existing.status !== 'waiting') return current

      let nextConnection: TaskConnection
      if (response === 'accepted') {
        nextConnection = { ...existing, status: 'accepted' }
        appendLog(`${queue.task.title} 작업의 도우미가 요청을 수락했어요.`)
      } else if (existing.candidateIndex + 1 < queue.candidates.length) {
        nextConnection = {
          candidateIndex: existing.candidateIndex + 1,
          status: 'waiting',
          retried: true,
        }
        appendLog(`${queue.task.title} 작업의 다음 후보에게 요청하고 있어요.`)
      } else {
        nextConnection = { ...existing, status: 'unmatched' }
        appendLog(`${queue.task.title} 작업은 후보 2명을 확인했지만 지원자가 없어요.`)
      }

      const next = { ...current, [taskId]: nextConnection }
      setStage(stageFromConnections(plan, next))
      return next
    })
  }

  const handleRequestComplete = (taskId: string) => {
    if (!plan) return
    const queue = plan.candidateQueues.find((item) => item.task.taskId === taskId)
    if (!queue) return

    setConnections((current) => {
      const existing = current[taskId]
      if (!existing || existing.status !== 'accepted') return current

      const next = {
        ...current,
        [taskId]: { ...existing, status: 'completed' as const },
      }
      appendLog(`${queue.task.title} 작업의 요청이 완료되었어요.`)
      setStage(stageFromConnections(plan, next))
      return next
    })
  }

  const resetDemo = () => {
    abortRef.current?.abort()
    setStage('form')
    setPlan(null)
    setConnections({})
    setLogs([])
    setErrorMessage('')
  }

  return (
    <main className="demo-shell">
      <section className="requester-panel" aria-labelledby="requester-heading">
        <div className="panel-inner panel-inner--requester">
          <header className="brand-row">
            <a className="brand" href="#top" aria-label="곁 홈">
              <span className="brand-symbol" aria-hidden="true">곁</span>
              <span>생활지원 연결</span>
            </a>
            <span className="demo-badge"><i aria-hidden="true" /> LIVE DEMO</span>
          </header>

          {stage === 'form' ? (
            <>
              <div className="intro" id="top">
                <p className="section-kicker">요청자 화면</p>
                <h1 id="requester-heading">어떤 도움이<br />필요하신가요?</h1>
                <p>필요한 일을 편하게 말씀해주세요. 에이전트가 일을 나누고 가까운 도우미를 찾아드려요.</p>
              </div>

              <form className="request-form" onSubmit={handleSubmit} noValidate>
                <div className="field">
                  <label htmlFor="requesterName">요청자 이름</label>
                  <input
                    id="requesterName"
                    value={form.requesterName}
                    onChange={(event) => updateForm('requesterName', event.target.value)}
                    aria-describedby={errors.requesterName ? 'requesterName-error' : undefined}
                    aria-invalid={Boolean(errors.requesterName)}
                    maxLength={40}
                  />
                  {errors.requesterName && <span className="field-error" id="requesterName-error">{errors.requesterName}</span>}
                </div>

                <div className="field">
                  <div className="label-row">
                    <label htmlFor="requestText">도움이 필요한 내용을 적어주세요</label>
                    <span>{form.requestText.length}/1200</span>
                  </div>
                  <textarea
                    id="requestText"
                    value={form.requestText}
                    onChange={(event) => updateForm('requestText', event.target.value)}
                    aria-describedby={errors.requestText ? 'requestText-error' : 'requestText-hint'}
                    aria-invalid={Boolean(errors.requestText)}
                    maxLength={1200}
                    rows={5}
                  />
                  <span className="field-hint" id="requestText-hint">여러 가지 도움이 필요해도 한 번에 말씀해주세요.</span>
                  {errors.requestText && <span className="field-error" id="requestText-error">{errors.requestText}</span>}
                </div>

                <fieldset className="schedule-fields">
                  <legend>도움이 필요한 일정</legend>
                  <div className="field field--date">
                    <label htmlFor="date">날짜</label>
                    <input id="date" type="date" value={form.date} onChange={(event) => updateForm('date', event.target.value)} aria-invalid={Boolean(errors.date)} />
                  </div>
                  <div className="field">
                    <label htmlFor="startTime">시작</label>
                    <input id="startTime" type="time" value={form.startTime} onChange={(event) => updateForm('startTime', event.target.value)} />
                  </div>
                  <span className="schedule-separator" aria-hidden="true">→</span>
                  <div className="field">
                    <label htmlFor="endTime">종료</label>
                    <input id="endTime" type="time" value={form.endTime} onChange={(event) => updateForm('endTime', event.target.value)} />
                  </div>
                  {(errors.date || errors.time) && <span className="field-error schedule-error">{errors.date ?? errors.time}</span>}
                </fieldset>

                <button className="submit-button" type="submit">
                  <span>도움 요청하기</span><span aria-hidden="true">→</span>
                </button>
              </form>
            </>
          ) : (
            <div className="request-status-view" id="top">
              <div className="care-hero">
                <CareFace stage={stage} />
                <p className="section-kicker">도움 신청 현황</p>
                <h1 id="requester-heading">
                  {stage === 'completed'
                    ? '요청한 도움이 완료되었어요'
                    : stage === 'matched'
                      ? '매칭이 완료되었어요'
                      : stage === 'unmatched' || stage === 'failed'
                        ? '연결 결과를 확인해주세요'
                        : stage === 'partially_completed'
                          ? '완료된 도움을 확인해주세요'
                          : stage === 'partially_matched'
                            ? '연결 결과를 확인해주세요'
                            : '도움을 요청할 이웃을 찾고 있어요'}
                </h1>
                {!isSuccessfulMatchingComplete && (
                  <p>
                    {stage === 'partially_completed'
                      ? '완료된 작업과 연결 결과를 아래에서 확인할 수 있어요.'
                      : stage === 'partially_matched'
                        ? '연결된 작업과 지원자가 없는 작업을 아래에서 확인할 수 있어요.'
                        : isTerminal
                          ? '각 작업의 최종 연결 상태를 아래에서 확인할 수 있어요.'
                          : '가까이 있고 시간이 맞는 이웃에게 차례대로 요청하고 있어요.'}
                  </p>
                )}
              </div>

              <section
                className={`connection-section ${isSuccessfulMatchingComplete ? 'connection-section--compact' : ''}`}
                aria-label={isSuccessfulMatchingComplete ? '작업별 도우미 연결 상태' : undefined}
                aria-labelledby={isSuccessfulMatchingComplete ? undefined : 'connection-heading'}
              >
                {!isSuccessfulMatchingComplete && (
                  <>
                    <h2 id="connection-heading">
                      {plan ? `도우미 ${plan.tasks.length}명에게 나눠 요청해요` : '요청을 안전하게 나누고 있어요'}
                    </h2>
                    <p>같은 시각에 겹친 일은 여러 이웃에게 나눠 요청하며, 작업마다 후보를 최대 2명까지 확인해요.</p>
                  </>
                )}

                <div className="connection-list">
                  {plan?.candidateQueues.map((queue, index) => {
                    const copy = connectionCopy(queue, connections[queue.task.taskId])
                    return (
                      <article className={`connection-row connection-row--${copy.tone}`} key={queue.task.taskId}>
                        <span className="connection-label">도우미 {index + 1}</span>
                        <div className="connection-main">
                          <h3>{copy.title}</h3>
                          <p>{queue.task.title}</p>
                        </div>
                        <span className="connection-badge">{copy.badge}</span>
                      </article>
                    )
                  })}
                  {!plan && (
                    <div className="connection-skeleton" aria-label="작업 분석 중">
                      <span /><span /><span />
                    </div>
                  )}
                </div>
              </section>

              <AgentConsole logs={logs} isLoading={isLoading} completed={agentCompleted} errorMessage={errorMessage} />
              {isTerminal && (
                <button className="reset-button" type="button" onClick={resetDemo}>새 도움 요청 작성</button>
              )}
            </div>
          )}
        </div>
      </section>

      <section className="helpers-panel" aria-labelledby="helpers-heading">
        <div className="panel-inner panel-inner--helpers">
          <header className="helpers-header">
            <div>
              <p className="section-kicker section-kicker--light">도우미 화면</p>
              <h2 id="helpers-heading">가까운 이웃에게<br />요청이 도착합니다</h2>
            </div>
          </header>

          {!plan ? (
            <div className={`helper-empty ${stage === 'matching' ? 'helper-empty--loading' : ''}`}>
              <div className="empty-radar" aria-hidden="true"><span /><span /><i>+</i></div>
              <h3>{stage === 'matching' ? '도우미 후보를 살펴보고 있어요' : '도움 요청을 기다리고 있어요'}</h3>
              <p>{stage === 'matching' ? '가능 시간과 거리를 확인해 작업별 후보를 찾습니다.' : '왼쪽에서 요청을 작성하면 도우미 화면을 미리 볼 수 있어요.'}</p>
            </div>
          ) : (
            <>
              {!allRequestsCompleted && (
                <div className="plan-summary"><span>요청 분석 완료</span><p>{plan.requestSummary}</p></div>
              )}
              <div className="helper-list">
                {activeAssignments.map(({ assignment, connection }) => (
                  <HelperCard
                    key={assignment.task.taskId}
                    assignment={assignment}
                    status={
                      connection.status === 'completed'
                        ? 'completed'
                        : connection.status === 'accepted'
                          ? 'accepted'
                          : 'pending'
                    }
                    attempt={connection.candidateIndex + 1}
                    onRespond={(response) => handleHelperResponse(assignment.task.taskId, response)}
                    onRequestComplete={() => handleRequestComplete(assignment.task.taskId)}
                  />
                ))}
              </div>
              {activeAssignments.length === 0 && (
                <div className="all-responses-finished" role="status">
                  <span aria-hidden="true">✓</span>
                  <h3>모든 응답 확인이 끝났어요</h3>
                  <p>왼쪽 화면에서 작업별 최종 연결 상태를 확인해주세요.</p>
                </div>
              )}
            </>
          )}
        </div>
      </section>
    </main>
  )
}
