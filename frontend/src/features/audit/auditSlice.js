import { createAsyncThunk, createSlice } from '@reduxjs/toolkit'
import { fetchAuditTrail } from '../../app/api'

export const loadAuditTrail = createAsyncThunk(
  'audit/load',
  async (complaintId, { rejectWithValue }) => {
    try {
      return (await fetchAuditTrail(complaintId)).entries
    } catch (err) {
      return rejectWithValue(err.message)
    }
  },
)

const auditSlice = createSlice({
  name: 'audit',
  initialState: { entries: [], open: false, loading: false, error: null },
  reducers: {
    drawerOpened: (s) => void (s.open = true),
    drawerClosed: (s) => void (s.open = false),
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadAuditTrail.pending, (s) => {
        s.loading = true
        s.error = null
      })
      .addCase(loadAuditTrail.fulfilled, (s, a) => {
        s.loading = false
        s.entries = a.payload
      })
      .addCase(loadAuditTrail.rejected, (s, a) => {
        s.loading = false
        s.error = a.payload || 'Could not load the audit trail'
      })
  },
})

export const { drawerOpened, drawerClosed } = auditSlice.actions
export default auditSlice.reducer
