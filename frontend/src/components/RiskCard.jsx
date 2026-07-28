import { useSelector } from 'react-redux'
import { AlertTriangle, ShieldAlert } from 'lucide-react'

const TONE = { Critical: 'critical', Major: 'major', Minor: 'minor' }
const BAR = { Critical: 'var(--critical)', Major: 'var(--major)', Minor: 'var(--minor)' }

export default function RiskCard() {
  const risk = useSelector((s) => s.assessment.risk)
  if (!risk) return null

  const tone = TONE[risk.severity] ?? 'neutral'

  return (
    <div className="panel">
      <div className="panel-title">
        <ShieldAlert size={13} />
        AI Copilot Risk Assessment
      </div>

      <div className="risk-head">
        <span className={`pill ${tone}`}>{risk.severity} Severity</span>
        <span className="pill neutral">{risk.priority} Priority</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-3)' }}>
          {risk.risk_score}/100
        </span>
      </div>

      <div className="meter" style={{ marginBottom: 10 }}>
        <div style={{ width: `${risk.risk_score}%`, background: BAR[risk.severity] ?? 'var(--primary)' }} />
      </div>

      <p className="justification">{risk.justification}</p>

      {risk.patient_safety_impact && (
        <p className="justification" style={{ fontSize: 12 }}>
          <strong>Patient safety:</strong> {risk.patient_safety_impact}
        </p>
      )}

      {risk.next_actions?.length > 0 && (
        <>
          <div className="panel-title" style={{ marginTop: 12 }}>Recommended Next Actions</div>
          <ol className="action-list">
            {risk.next_actions.map((action, i) => (
              <li key={i}>
                <span className="step">{i + 1}</span>
                <span>{action}</span>
              </li>
            ))}
          </ol>
        </>
      )}

      {risk.regulatory_flags?.map((flag, i) => (
        <div className="flag" key={i}>
          <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>{flag}</span>
        </div>
      ))}
    </div>
  )
}
