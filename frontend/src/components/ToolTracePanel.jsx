import { Activity, CheckCircle, AlertCircle, AlertTriangle, Info, Terminal } from 'lucide-react'

// Determine visual style of a step based on its content
function classifyStep(step) {
  const text = (step.step + ' ' + (step.detail || '')).toLowerCase()
  if (text.includes('error') || text.includes('❌')) return 'step-err'
  if (text.includes('⚠️') || text.includes('warning') || text.includes('cache miss')) return 'step-warn'
  if (text.includes('agent finished') || text.includes('complete') || text.includes('computed')) return 'step-ok'
  if (text.includes('calling') || text.includes('executing') || text.includes('→')) return 'step-tool'
  return 'step-info'
}

function StepIcon({ cls }) {
  const props = { size: 12, style: { flexShrink: 0 } }
  if (cls === 'step-err')  return <AlertCircle   {...props} color="var(--red)"    />
  if (cls === 'step-warn') return <AlertTriangle  {...props} color="var(--amber)"  />
  if (cls === 'step-ok')   return <CheckCircle    {...props} color="var(--green)"  />
  if (cls === 'step-tool') return <Terminal       {...props} color="var(--accent)" />
  return <Info {...props} color="var(--purple)" />
}

function TraceStep({ step, index }) {
  const cls = classifyStep(step)
  return (
    <div className={`trace-step ${cls}`}>
      <div className="trace-step-index">#{String(index + 1).padStart(2, '0')}</div>
      <div className="trace-step-name">
        <StepIcon cls={cls} />
        {step.step}
      </div>
      {step.detail && (
        <div className="trace-step-detail">{step.detail}</div>
      )}
    </div>
  )
}

function LoadingSkeletons() {
  return (
    <div className="trace-loading">
      {[1, 2, 3].map((i) => (
        <div key={i} className="trace-skeleton" />
      ))}
      <div style={{ textAlign: 'center', fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
        Executing tools…
      </div>
    </div>
  )
}

export default function ToolTracePanel({ steps, loading }) {
  return (
    <div className="trace-panel">
      {/* Header */}
      <div className="trace-header">
        <Activity size={14} color="var(--accent)" />
        <span className="trace-header-title">Tool Trace</span>
        {steps.length > 0 && (
          <span className="trace-count">{steps.length} steps</span>
        )}
      </div>

      {/* Content */}
      <div className="trace-steps">
        {loading ? (
          <LoadingSkeletons />
        ) : steps.length === 0 ? (
          <div className="trace-empty">
            <Activity size={32} color="var(--text-muted)" strokeWidth={1.5} />
            <div>
              <p style={{ fontWeight: 600, marginBottom: '4px' }}>No trace yet</p>
              <p style={{ fontSize: '11px' }}>
                Tool calls will appear here in real-time as the agent works through your question.
              </p>
            </div>
          </div>
        ) : (
          steps.map((step, i) => (
            <TraceStep key={i} step={step} index={i} />
          ))
        )}
      </div>
    </div>
  )
}
