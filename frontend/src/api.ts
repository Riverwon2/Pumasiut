import type { AssignmentPlan, HelpRequestInput, StreamEvent } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? ''

function decodeEvent(block: string): StreamEvent | null {
  const lines = block.split('\n')
  const eventName = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
  const dataText = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')

  if (!eventName || !dataText) return null

  const data: unknown = JSON.parse(dataText)
  if (eventName === 'phase') {
    return { type: 'phase', data: data as { message: string } }
  }
  if (eventName === 'result') {
    return { type: 'result', data: data as AssignmentPlan }
  }
  if (eventName === 'error') {
    return { type: 'error', data: data as { message: string } }
  }
  return null
}

export function parseSseChunk(
  buffer: string,
): { events: StreamEvent[]; remainder: string } {
  const normalized = buffer.replace(/\r\n/g, '\n')
  const blocks = normalized.split('\n\n')
  const remainder = blocks.pop() ?? ''
  const events = blocks
    .map(decodeEvent)
    .filter((event): event is StreamEvent => event !== null)
  return { events, remainder }
}

export async function streamHelpRequest(
  input: HelpRequestInput,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_URL}/api/requests/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
    signal,
  })

  if (!response.ok) {
    let message = '요청 정보를 확인해주세요.'
    try {
      const payload = (await response.json()) as { detail?: unknown }
      if (typeof payload.detail === 'string') message = payload.detail
    } catch {
      // Preserve the user-safe default message.
    }
    throw new Error(message)
  }

  if (!response.body) {
    throw new Error('실시간 응답을 시작하지 못했습니다.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const parsed = parseSseChunk(buffer)
    buffer = parsed.remainder
    parsed.events.forEach(onEvent)
    if (done) break
  }

  if (buffer.trim()) {
    const trailing = decodeEvent(buffer)
    if (trailing) onEvent(trailing)
  }
}

