import { useSelector } from 'react-redux'
import { Wrench } from 'lucide-react'

function ActionList({ title, items }) {
  if (!items?.length) return null
  return (
    <>
      <div className="panel-title" style={{ marginTop: 12 }}>{title}</div>
      <ol className="action-list">
        {items.map((item, i) => (
          <li key={i}>
            <span className="step">{i + 1}</span>
            <span>{item}</span>
          </li>
        ))}
      </ol>
    </>
  )
}

export default function CapaCard() {
  const capa = useSelector((s) => s.assessment.capa)
  if (!capa) return null

  return (
    <div className="panel">
      <div className="panel-title">
        <Wrench size={13} />
        Root Cause &amp; CAPA Recommendation
        <span className="pill neutral" style={{ marginLeft: 'auto' }}>
          {capa.investigation_type}
        </span>
      </div>

      {capa.probable_root_causes?.map((cause, i) => (
        <div className="cause" key={i}>
          <span className="cat">{cause.category}</span>
          <span>
            {cause.cause}
            <span style={{ color: 'var(--text-3)' }}> — {cause.likelihood} likelihood</span>
          </span>
        </div>
      ))}

      {capa.immediate_correction && (
        <p className="justification" style={{ marginTop: 10 }}>
          <strong>Immediate correction:</strong> {capa.immediate_correction}
        </p>
      )}

      <ActionList title="Corrective Actions" items={capa.corrective_actions} />
      <ActionList title="Preventive Actions" items={capa.preventive_actions} />
    </div>
  )
}
