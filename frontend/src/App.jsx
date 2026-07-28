import { useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import AuditDrawer from './components/AuditDrawer'
import ComplaintForm from './components/ComplaintForm'
import CopilotPanel from './components/CopilotPanel'
import ModelBadge from './components/ModelBadge'
import { bootstrap } from './app/turnThunks'

export default function App() {
  const dispatch = useDispatch()
  const ready = useSelector((s) => s.session.ready)

  useEffect(() => {
    dispatch(bootstrap()).catch?.(() => {})
  }, [dispatch])

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark">AI</div>
          <div>
            <h1>AIVOA · Customer Complaint Management</h1>
            <p>Pharmaceutical QMS · API &amp; FDF</p>
          </div>
        </div>
        <div className="header-actions">
          <ModelBadge />
          <span className="pill neutral">{ready ? 'Session active' : 'Connecting…'}</span>
        </div>
      </header>

      <main className="workspace">
        <ComplaintForm />
        <CopilotPanel />
      </main>

      <AuditDrawer />
    </div>
  )
}
