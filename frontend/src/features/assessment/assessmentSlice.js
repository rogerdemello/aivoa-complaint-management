import { createSlice } from '@reduxjs/toolkit'

/** Everything the AI Copilot panel derives from the complaint. */
const initialState = {
  risk: null,
  completeness: null,
  capa: null,
  duplicates: null,
  summary: null,
}

const assessmentSlice = createSlice({
  name: 'assessment',
  initialState,
  reducers: {
    riskReceived: (s, a) => void (s.risk = a.payload),
    completenessReceived: (s, a) => void (s.completeness = a.payload),
    capaReceived: (s, a) => void (s.capa = a.payload),
    duplicatesReceived: (s, a) => void (s.duplicates = a.payload),
    summaryReceived: (s, a) => void (s.summary = a.payload),
    assessmentRestored: (s, a) => ({ ...initialState, ...a.payload }),
    assessmentCleared: () => initialState,
  },
})

export const {
  riskReceived,
  completenessReceived,
  capaReceived,
  duplicatesReceived,
  summaryReceived,
  assessmentRestored,
  assessmentCleared,
} = assessmentSlice.actions

export default assessmentSlice.reducer
