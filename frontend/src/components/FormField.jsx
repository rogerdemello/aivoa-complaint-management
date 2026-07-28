import { useRef, useState } from 'react'
import { useSelector } from 'react-redux'

/**
 * One form field.
 *
 * `readOnly` is set on every input, and no change handler exists at all - the
 * value can only arrive through a Redux action dispatched from the AI stream.
 * The provenance line underneath is what makes an AI-populated GMP record
 * defensible: it names the source and quotes the text the value came from.
 */

const LONG_FIELDS = new Set(['detailed_complaint_description'])
const DATE_FIELDS = new Set(['manufacturing_date', 'expiry_date', 'complaint_date'])

function EvidenceTip({ evidence, confidence }) {
  const [shown, setShown] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const anchor = useRef(null)

  if (!evidence) return null

  const show = () => {
    const rect = anchor.current?.getBoundingClientRect()
    if (rect) setPos({ top: rect.bottom + window.scrollY + 6, left: rect.left + window.scrollX })
    setShown(true)
  }

  return (
    <>
      <span
        ref={anchor}
        className="evidence-trigger"
        onMouseEnter={show}
        onMouseLeave={() => setShown(false)}
      >
        evidence
      </span>
      {shown && (
        <span className="evidence-tip" style={{ top: pos.top, left: pos.left }}>
          <span className="tip-label">Extracted from</span>
          <span className="quote">“{evidence}”</span>
          {confidence != null && (
            <span className="tip-label" style={{ marginTop: 5, marginBottom: 0 }}>
              confidence {Math.round(confidence * 100)}%
            </span>
          )}
        </span>
      )}
    </>
  )
}

export default function FormField({ name, label, required }) {
  const field = useSelector((s) => s.complaint.fields[name])
  const patchedAt = useSelector((s) => s.complaint.patchedAt[name])

  const value = field?.value ?? ''
  const hasValue = value !== '' && value != null
  const isFresh = patchedAt && Date.now() - patchedAt < 1600

  const className = [
    'field-input',
    hasValue ? 'filled' : 'empty',
    isFresh ? 'just-patched' : '',
  ]
    .filter(Boolean)
    .join(' ')

  const shared = {
    className,
    value: hasValue ? String(value) : '',
    placeholder: 'Awaiting AI extraction...',
    readOnly: true,
    'aria-readonly': true,
    tabIndex: -1,
    // No onChange: this input is a display surface, not a control.
  }

  return (
    <div className={`field ${LONG_FIELDS.has(name) ? 'span-2' : ''}`}>
      <label htmlFor={name}>
        {label}
        {required && <span className="required" title="Mandatory for a complete record">*</span>}
      </label>

      {LONG_FIELDS.has(name) ? (
        <textarea id={name} rows={3} {...shared} />
      ) : (
        <input id={name} type={DATE_FIELDS.has(name) && hasValue ? 'text' : 'text'} {...shared} />
      )}

      {hasValue && field?.source && (
        <div className="provenance">
          <span className={`src-badge ${field.source}`}>{field.source}</span>
          <EvidenceTip evidence={field.evidence} confidence={field.confidence} />
        </div>
      )}
    </div>
  )
}
