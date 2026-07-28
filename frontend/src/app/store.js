import { configureStore } from '@reduxjs/toolkit'

import assessmentReducer from '../features/assessment/assessmentSlice'
import auditReducer from '../features/audit/auditSlice'
import complaintReducer from '../features/complaint/complaintSlice'
import copilotReducer from '../features/copilot/copilotSlice'
import sessionReducer from '../features/session/sessionSlice'

export const store = configureStore({
  reducer: {
    session: sessionReducer,
    complaint: complaintReducer,
    copilot: copilotReducer,
    assessment: assessmentReducer,
    audit: auditReducer,
  },
})
