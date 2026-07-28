import { useSelector } from 'react-redux'
import { CheckCircle2, ClipboardList } from 'lucide-react'

export default function CompletenessMeter() {
  const completeness = useSelector((s) => s.assessment.completeness)
  if (!completeness) return null

  const { score, missing_required: missing = [], ready_to_submit: ready } = completeness

  return (
    <div className="panel">
      <div className="panel-title">
        <ClipboardList size={13} />
        Complaint Completeness
        <span style={{ marginLeft: 'auto', textTransform: 'none', letterSpacing: 0 }}>
          {score}%
        </span>
      </div>

      <div className="meter" style={{ marginBottom: 10 }}>
        <div
          style={{
            width: `${score}%`,
            background: ready ? 'var(--ok)' : score >= 60 ? 'var(--warn)' : 'var(--critical)',
          }}
        />
      </div>

      {ready ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--ok)' }}>
          <CheckCircle2 size={14} />
          All mandatory fields captured — ready for QA review.
        </div>
      ) : (
        missing.map((item) => (
          <div className="missing-item" key={item.field}>
            <div className="fname">{item.field.replace(/_/g, ' ')}</div>
            <div className="why">{item.why_it_matters}</div>
            <div className="ask">“{item.question_to_ask}”</div>
          </div>
        ))
      )}
    </div>
  )
}
