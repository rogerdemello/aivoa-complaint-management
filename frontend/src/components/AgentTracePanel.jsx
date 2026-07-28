import { useSelector } from 'react-redux'
import { Workflow } from 'lucide-react'

/**
 * Live LangGraph execution for the current turn.
 *
 * Every node the graph visits appears here as it completes, with the model
 * that served it and how long it took — which is exactly the walkthrough the
 * assignment's second video asks for, visible without opening a terminal.
 */
export default function AgentTracePanel() {
  const trace = useSelector((s) => s.copilot.trace)
  const streaming = useSelector((s) => s.copilot.streaming)

  if (!trace.length && !streaming) return null

  return (
    <div className="panel">
      <div className="panel-title">
        <Workflow size={13} />
        LangGraph Execution
        {streaming && <span className="spinner" style={{ marginLeft: 'auto' }} />}
      </div>

      <div className="trace">
        {trace.map((event, i) => (
          <div className={`trace-row ${event.status === 'error' ? 'error' : ''}`} key={i}>
            <span className="node">{event.node}</span>
            <span className="detail">{event.detail}</span>
            {event.duration_ms != null && <span className="ms">{event.duration_ms}ms</span>}
          </div>
        ))}
      </div>

      {trace.some((e) => e.model) && (
        <div style={{ marginTop: 8, fontSize: 10.5, color: 'var(--text-3)' }}>
          Models used:{' '}
          {[...new Set(trace.filter((e) => e.model).map((e) => e.model))].join(', ')}
        </div>
      )}
    </div>
  )
}
