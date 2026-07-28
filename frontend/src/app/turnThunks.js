/**
 * Translating the SSE stream into Redux actions.
 *
 * This is the seam between the LangGraph run and the UI: one graph node's
 * output becomes one dispatched action, so the form fills in progressively as
 * the agent works rather than snapping into place at the end.
 */

import {
  createSession,
  fetchFormSchema,
  fetchModelHealth,
  fetchSessionState,
  sendMessage,
  uploadDocument,
} from './api'
import {
  complaintReplaced,
  fieldPatched,
  schemaLoaded,
  schemaLoading,
} from '../features/complaint/complaintSlice'
import {
  assessmentRestored,
  capaReceived,
  completenessReceived,
  duplicatesReceived,
  riskReceived,
  summaryReceived,
} from '../features/assessment/assessmentSlice'
import {
  assistantMessageAdded,
  nodeVisited,
  turnFailed,
  turnFinished,
  turnStarted,
  userMessageAdded,
} from '../features/copilot/copilotSlice'
import {
  modelHealthReceived,
  sessionStarted,
  turnRecorded,
} from '../features/session/sessionSlice'

/** One SSE event -> zero or more dispatches. */
function handleEvent(dispatch, { event, data }) {
  switch (event) {
    case 'turn_start':
      dispatch(turnRecorded(data))
      break
    case 'node':
      dispatch(nodeVisited(data))
      break
    case 'field_patch':
      dispatch(fieldPatched(data))
      break
    case 'complaint':
      dispatch(complaintReplaced(data))
      break
    case 'risk':
      dispatch(riskReceived(data))
      break
    case 'completeness':
      dispatch(completenessReceived(data))
      break
    case 'capa':
      dispatch(capaReceived(data))
      break
    case 'duplicates':
      dispatch(duplicatesReceived(data))
      break
    case 'summary':
      dispatch(summaryReceived(data))
      break
    case 'error':
      // Non-fatal: a branch failed but the turn continues.
      dispatch(turnFailed(data.message))
      break
    case 'done':
      dispatch(turnRecorded(data))
      dispatch(assistantMessageAdded(data.assistant_message))
      dispatch(turnFinished())
      break
    default:
      break
  }
}

export const bootstrap = () => async (dispatch) => {
  dispatch(schemaLoading())
  const [{ session_id }, schema] = await Promise.all([createSession(), fetchFormSchema()])
  dispatch(sessionStarted(session_id))
  dispatch(schemaLoaded(schema.fields))

  // Non-blocking: the badge is informational.
  fetchModelHealth()
    .then((health) => dispatch(modelHealthReceived(health)))
    .catch(() => {})
}

export const restoreSession = (sessionId) => async (dispatch) => {
  const state = await fetchSessionState(sessionId)
  dispatch(complaintReplaced(state.complaint))
  dispatch(assessmentRestored(state))
  dispatch(turnRecorded(state))
}

export const runMessage = (text) => async (dispatch, getState) => {
  const { sessionId } = getState().session
  if (!sessionId || !text.trim()) return

  dispatch(userMessageAdded(text))
  dispatch(turnStarted())

  try {
    await sendMessage(sessionId, text, (evt) => handleEvent(dispatch, evt))
  } catch (err) {
    dispatch(turnFailed(err.message))
  } finally {
    dispatch(turnFinished())
  }
}

export const runUpload = (file) => async (dispatch, getState) => {
  const { sessionId } = getState().session
  if (!sessionId || !file) return

  dispatch(userMessageAdded(`📎 Uploaded **${file.name}**`))
  dispatch(turnStarted())

  try {
    await uploadDocument(sessionId, file, (evt) => handleEvent(dispatch, evt))
  } catch (err) {
    dispatch(turnFailed(err.message))
  } finally {
    dispatch(turnFinished())
  }
}
