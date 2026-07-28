import { useDispatch, useSelector } from 'react-redux'
import { ArrowRight, X } from 'lucide-react'

import { drawerClosed } from '../features/audit/auditSlice'

/**
 * The append-only field history.
 *
 * 21 CFR Part 11 §11.10(e) requires a computer-generated, time-stamped audit
 * trail that records changes without obscuring previously recorded values —
 * which is why old values are struck through rather than replaced.
 */
export default function AuditDrawer() {
  const dispatch = useDispatch()
  const { entries, open, loading, error } = useSelector((s) => s.audit)

  if (!open) return null

  const close = () => dispatch(drawerClosed())

  return (
    <>
      <div className="drawer-scrim" onClick={close} />
      <aside className="drawer" role="dialog" aria-label="Audit trail">
        <div className="card-head">
          <div>
            <h2>Audit Trail</h2>
            <p>Append-only field history · 21 CFR Part 11 §11.10(e)</p>
          </div>
          <button className="btn icon" onClick={close} aria-label="Close">
            <X size={15} />
          </button>
        </div>

        <div className="drawer-body">
          {loading && <div className="empty-note">Loading…</div>}
          {error && <div className="error-banner">{error}</div>}
          {!loading && !error && !entries.length && (
            <div className="empty-note">No changes recorded yet.</div>
          )}

          {entries.map((entry) => (
            <div className="audit-row" key={entry.id}>
              <div className="when">
                {entry.created_at ? new Date(entry.created_at).toLocaleString() : '—'}
                <div style={{ marginTop: 2 }}>turn {entry.turn_id}</div>
              </div>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 3 }}>{entry.label}</div>
                <div className="change">
                  {entry.old_value ? <span className="old">{entry.old_value}</span> : <span style={{ color: 'var(--text-3)' }}>(empty)</span>}
                  <ArrowRight size={12} style={{ color: 'var(--text-3)' }} />
                  <span className="new">{entry.new_value}</span>
                </div>
                <div className="meta">
                  {entry.actor} · {entry.source} · {entry.model}
                </div>
                {entry.evidence && (
                  <div className="meta" style={{ fontStyle: 'italic' }}>“{entry.evidence}”</div>
                )}
              </div>
            </div>
          ))}
        </div>
      </aside>
    </>
  )
}
