import { useEffect, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { SendHorizonal, Sparkles, UploadCloud } from 'lucide-react'

import AgentTracePanel from './AgentTracePanel'
import CapaCard from './CapaCard'
import CompletenessMeter from './CompletenessMeter'
import DuplicateAlert from './DuplicateAlert'
import RiskCard from './RiskCard'
import { runMessage, runUpload } from '../app/turnThunks'

const ACCEPT = '.pdf,.eml,.txt,.md,.json'

/** Minimal **bold** rendering — the assistant's replies are the only source. */
function RichText({ text }) {
  return (
    <>
      {String(text)
        .split('\n\n')
        .map((para, i) => (
          <p key={i}>
            {para.split(/(\*\*[^*]+\*\*)/g).map((chunk, j) =>
              chunk.startsWith('**') && chunk.endsWith('**') ? (
                <strong key={j}>{chunk.slice(2, -2)}</strong>
              ) : (
                <span key={j}>{chunk}</span>
              ),
            )}
          </p>
        ))}
    </>
  )
}

export default function CopilotPanel() {
  const dispatch = useDispatch()
  const { messages, streaming, error } = useSelector((s) => s.copilot)
  const ready = useSelector((s) => s.session.ready)

  const [draft, setDraft] = useState('')
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef(null)
  const scroller = useRef(null)

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' })
  }, [messages, streaming])

  const submit = () => {
    const text = draft.trim()
    if (!text || streaming || !ready) return
    setDraft('')
    dispatch(runMessage(text))
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file && !streaming) dispatch(runUpload(file))
  }

  const onPick = (e) => {
    const file = e.target.files?.[0]
    if (file) dispatch(runUpload(file))
    e.target.value = ''
  }

  return (
    <section className="card copilot">
      <div className="card-head">
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <Sparkles size={15} style={{ color: 'var(--primary)' }} />
            AIVOA Copilot
          </h2>
          <p>AI Complaint Intake Assistant</p>
        </div>
        <span className="pill neutral">BETA</span>
      </div>

      <div
        className={`dropzone ${dragging ? 'dragging' : ''}`}
        onClick={() => !streaming && fileInput.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <UploadCloud size={20} style={{ color: 'var(--primary)' }} />
        <div style={{ marginTop: 5 }}>
          Drag &amp; drop a complaint document, or <strong>click to browse</strong>
        </div>
        <span className="hint">PDF · EML · TXT — up to 10 MB</span>
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          onChange={onPick}
          style={{ display: 'none' }}
        />
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="messages" ref={scroller}>
        {messages.map((message, i) => (
          <div className={`msg ${message.role}`} key={i}>
            <RichText text={message.content} />
          </div>
        ))}
        {streaming && (
          <div className="msg assistant" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="spinner" />
            <span style={{ color: 'var(--text-3)' }}>Working through the graph…</span>
          </div>
        )}
      </div>

      <div className="composer">
        <textarea
          rows={2}
          value={draft}
          placeholder="Describe the complaint, or correct a detail…"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={!ready}
        />
        <button
          className="btn primary"
          onClick={submit}
          disabled={streaming || !draft.trim() || !ready}
          aria-label="Send"
        >
          <SendHorizonal size={15} />
        </button>
      </div>

      <AgentTracePanel />
      <RiskCard />
      <CompletenessMeter />
      <DuplicateAlert />
      <CapaCard />

      <div style={{ padding: '8px 16px 12px', fontSize: 10.5, color: 'var(--text-3)' }}>
        AI responses may contain errors. Verify against the source document before QA release.
      </div>
    </section>
  )
}
