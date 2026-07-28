import { useSelector } from 'react-redux'

/**
 * Which Groq model is really serving each graph role.
 *
 * The assignment mandates `gemma2-9b-it`, which Groq decommissioned in
 * October 2025. The backend falls back to a live model rather than failing —
 * this badge makes that substitution visible instead of silent.
 */
export default function ModelBadge() {
  const health = useSelector((s) => s.session.modelHealth)
  if (!health?.roles?.length) return null

  const substituted = health.roles.filter((r) => r.substituted)
  const title = health.roles
    .map((r) => `${r.role}: ${r.resolved}${r.substituted ? ` (configured ${r.configured} — ${r.reason})` : ''}`)
    .join('\n')

  return (
    <span className={`model-badge ${substituted.length ? 'substituted' : ''}`} title={title}>
      <span className="dot" />
      {substituted.length
        ? `${substituted.length} model${substituted.length === 1 ? '' : 's'} substituted`
        : `${health.roles.length} models live`}
    </span>
  )
}
