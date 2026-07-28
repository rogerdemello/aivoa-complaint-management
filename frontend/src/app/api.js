/**
 * API helpers.
 *
 * Both AI entry points stream Server-Sent Events over a POST, so `EventSource`
 * is unusable (it only issues GETs). `streamPost` reads the response body and
 * parses the SSE framing by hand.
 */

const BASE = '/api'

export async function createSession() {
  const res = await fetch(`${BASE}/sessions`, { method: 'POST' })
  if (!res.ok) throw new Error(`Could not start a session (${res.status})`)
  return res.json()
}

export async function fetchFormSchema() {
  const res = await fetch(`${BASE}/form-schema`)
  if (!res.ok) throw new Error(`Could not load the form schema (${res.status})`)
  return res.json()
}

export async function fetchModelHealth() {
  const res = await fetch(`${BASE}/health/models`)
  if (!res.ok) throw new Error(`Model health unavailable (${res.status})`)
  return res.json()
}

export async function fetchAuditTrail(complaintId) {
  const res = await fetch(`${BASE}/complaint/${complaintId}/audit`)
  if (!res.ok) throw new Error(`Could not load the audit trail (${res.status})`)
  return res.json()
}

export async function fetchSessionState(sessionId) {
  const res = await fetch(`${BASE}/complaint/session/${sessionId}`)
  if (!res.ok) throw new Error(`Could not restore the session (${res.status})`)
  return res.json()
}

/**
 * POST and consume an SSE response, invoking `onEvent({event, data})` per frame.
 */
async function streamPost(url, init, onEvent) {
  const res = await fetch(url, init)

  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      /* response wasn't JSON; keep the status-based message */
    }
    throw new Error(detail)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Frames are separated by a blank line. The trailing element is a partial
    // frame, so it stays in the buffer until more bytes arrive.
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      let name = 'message'
      const dataLines = []

      for (const line of frame.split('\n')) {
        if (line.startsWith(':')) continue // keep-alive comment
        if (line.startsWith('event:')) name = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }

      if (!dataLines.length) continue
      try {
        onEvent({ event: name, data: JSON.parse(dataLines.join('\n')) })
      } catch {
        // A malformed frame shouldn't kill the whole stream.
        console.warn('Unparseable SSE frame', frame)
      }
    }
  }
}

export function sendMessage(sessionId, text, onEvent, signal) {
  return streamPost(
    `${BASE}/complaint/message`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, text }),
      signal,
    },
    onEvent,
  )
}

export function uploadDocument(sessionId, file, onEvent, signal) {
  const form = new FormData()
  form.append('session_id', sessionId)
  form.append('file', file)
  return streamPost(`${BASE}/complaint/document`, { method: 'POST', body: form, signal }, onEvent)
}
