import { createSlice } from '@reduxjs/toolkit'

const initialState = {
  sessionId: null,
  complaintId: null,
  referenceNo: null,
  turnId: 0,
  modelHealth: null,
  ready: false,
}

const sessionSlice = createSlice({
  name: 'session',
  initialState,
  reducers: {
    sessionStarted(state, action) {
      state.sessionId = action.payload
      state.ready = true
    },
    turnRecorded(state, action) {
      const { turn_id, reference_no, complaint_id } = action.payload || {}
      if (turn_id) state.turnId = turn_id
      if (reference_no) state.referenceNo = reference_no
      if (complaint_id) state.complaintId = complaint_id
    },
    modelHealthReceived(state, action) {
      state.modelHealth = action.payload
    },
    sessionReset(state) {
      state.complaintId = null
      state.referenceNo = null
      state.turnId = 0
    },
  },
})

export const { sessionStarted, turnRecorded, modelHealthReceived, sessionReset } =
  sessionSlice.actions

export default sessionSlice.reducer
