import { useDispatch, useSelector } from 'react-redux'
import { FileClock, Lock, Save, Sparkles } from 'lucide-react'

import FormField from './FormField'
import { drawerOpened, loadAuditTrail } from '../features/audit/auditSlice'
import { selectFilledCount } from '../features/complaint/complaintSlice'

/** The four sections of the reference UI, and which fields belong to each. */
const SECTIONS = [
  { title: '1. Origin & Customer Details', fields: ['complaint_source', 'customer_name'] },
  {
    title: '2. Product & Batch Identification',
    fields: [
      'product_name',
      'product_strength_grade',
      'batch_lot_number',
      'manufacturing_date',
      'expiry_date',
      'quantity_affected',
      'quantity_unit',
    ],
  },
  {
    title: '3. Complaint Details',
    fields: ['complaint_type', 'complaint_date', 'detailed_complaint_description'],
  },
  { title: '4. Initial Assessment & Priority', fields: ['initial_severity', 'priority'] },
]

export default function ComplaintForm() {
  const dispatch = useDispatch()
  const schema = useSelector((s) => s.complaint.schema)
  const filled = useSelector(selectFilledCount)
  const { referenceNo, complaintId } = useSelector((s) => s.session)

  const byName = Object.fromEntries(schema.map((f) => [f.name, f]))

  const openAudit = () => {
    if (!complaintId) return
    dispatch(loadAuditTrail(complaintId))
    dispatch(drawerOpened())
  }

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Log Customer Complaint</h2>
          <p>API &amp; FDF Quality Assurance Module</p>
        </div>
        <div className="header-actions">
          {referenceNo && <span className="pill neutral">{referenceNo}</span>}
          <span className="pill neutral">{filled} field{filled === 1 ? '' : 's'} filled</span>
        </div>
      </div>

      <div className="card-body">
        <div className="readonly-note">
          <Lock size={13} />
          This form is populated only by the AI Copilot. Manual entry is disabled by design.
        </div>

        {SECTIONS.map((section) => (
          <div key={section.title}>
            <div className="section-label">{section.title}</div>
            <div className="field-grid">
              {section.fields.map((name) => (
                <FormField
                  key={name}
                  name={name}
                  label={byName[name]?.label ?? name}
                  required={byName[name]?.required}
                />
              ))}
            </div>
          </div>
        ))}

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: 8,
            marginTop: 22,
            paddingTop: 14,
            borderTop: '1px solid var(--border)',
          }}
        >
          <button className="btn" onClick={openAudit} disabled={!complaintId}>
            <FileClock size={14} />
            Audit Trail
          </button>
          <button className="btn primary" disabled title="Records are saved automatically each turn">
            <Save size={14} />
            Saved automatically
          </button>
        </div>

        {filled === 0 && (
          <div className="empty-note">
            <Sparkles size={16} style={{ opacity: 0.5 }} />
            <br />
            Describe a complaint or upload a document in the Copilot to populate this form.
          </div>
        )}
      </div>
    </section>
  )
}
