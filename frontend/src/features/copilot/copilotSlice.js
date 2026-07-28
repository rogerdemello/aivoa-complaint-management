import { createSlice } from '@reduxjs/toolkit'

const initialState = {
  messages: [
    {
      role: 'assistant',
      content:
        'Upload a complaint document or describe the complaint, and I will extract the details and populate the form for you.',
    },
  ],
  trace: [],       // live LangGraph node execution for the current turn
  streaming: false,
  error: null,
}

const copilotSlice = createSlice({
  name: 'copilot',
  initialState,
  reducers: {
    userMessageAdded(state, action) {
      state.messages.push({ role: 'user', content: action.payload })
    },
    assistantMessageAdded(state, action) {
      if (action.payload) state.messages.push({ role: 'assistant', content: action.payload })
    },
    turnStarted(state) {
      state.streaming = true
      state.error = null
      state.trace = []          // trace is per-turn in the UI
    },
    nodeVisited(state, action) {
      state.trace.push(action.payload)
    },
    turnFinished(state) {
      state.streaming = false
    },
    turnFailed(state, action) {
      state.streaming = false
      state.error = action.payload
    },
    copilotCleared: () => initialState,
  },
})

export const {
  userMessageAdded,
  assistantMessageAdded,
  turnStarted,
  nodeVisited,
  turnFinished,
  turnFailed,
  copilotCleared,
} = copilotSlice.actions

export default copilotSlice.reducer
