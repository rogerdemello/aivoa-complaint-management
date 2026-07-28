import { useSelector } from 'react-redux'
import { Copy } from 'lucide-react'

export default function DuplicateAlert() {
  const duplicates = useSelector((s) => s.assessment.duplicates)
  if (!duplicates?.length) return null

  return (
    <div className="panel">
      <div className="panel-title">
        <Copy size={13} />
        Possible Duplicates &amp; Trends
      </div>

      {duplicates.map((match) => (
        <div className="dup-item" key={match.reference_no}>
          <div>
            <div className="ref">{match.reference_no}</div>
            <div className="reason">{match.reason}</div>
            {match.batch_lot_number && (
              <div className="reason" style={{ color: 'var(--text-3)' }}>
                {match.product_name} · batch {match.batch_lot_number}
              </div>
            )}
          </div>
          <span className="pill neutral" style={{ alignSelf: 'flex-start', flexShrink: 0 }}>
            {Math.round((match.similarity ?? 0) * 100)}%
          </span>
        </div>
      ))}
    </div>
  )
}
