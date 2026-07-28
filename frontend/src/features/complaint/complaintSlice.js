import { createSlice } from '@reduxjs/toolkit'

/**
 * The left-hand form.
 *
 * Nothing here is ever set by a keystroke. Every reducer is driven by an event
 * from the AI stream, which is what enforces the "do not fill the form
 * manually" constraint at the state level rather than merely in the markup.
 */
const initialState = {
  schema: [],
  fields: {},        // name -> { value, confidence, evidence, source, turn_id }
  patchedAt: {},     // name -> timestamp, drives the fill animation
  loadingSchema: false,
}

const complaintSlice = createSlice({
  name: 'complaint',
  initialState,
  reducers: {
    schemaLoaded(state, action) {
      state.schema = action.payload
      state.loadingSchema = false
    },
    schemaLoading(state) {
      state.loadingSchema = true
    },
    /** A single field arrived from `merge_complaint`. */
    fieldPatched(state, action) {
      const { field, new_value, evidence, confidence, source } = action.payload
      state.fields[field] = {
        value: new_value,
        evidence,
        confidence,
        source,
      }
      state.patchedAt[field] = Date.now()
    },
    /** The whole record, e.g. when restoring a session. */
    complaintReplaced(state, action) {
      state.fields = action.payload || {}
    },
    cleared(state) {
      state.fields = {}
      state.patchedAt = {}
    },
  },
})

export const { schemaLoaded, schemaLoading, fieldPatched, complaintReplaced, cleared } =
  complaintSlice.actions

export const selectField = (name) => (s) => s.complaint.fields[name]
export const selectFilledCount = (s) =>
  Object.values(s.complaint.fields).filter((f) => f?.value != null && f.value !== '').length

export default complaintSlice.reducer
