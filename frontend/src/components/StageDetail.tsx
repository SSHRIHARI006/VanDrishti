import { fileUrl } from '../api'
import type { Job, Stage } from '../types'

function fmt(v: unknown): string {
  if (v === null || v === undefined) return '–'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toLocaleString(undefined, { maximumFractionDigits: 2 })
  if (typeof v === 'object') return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k}: ${fmt(x)}`).join(', ')
  return String(v)
}

const label = (k: string) => k.replace(/_/g, ' ').replace(/\b(pct)\b/, '%').replace(/\bm2\b/, 'm²')

export default function StageDetail({ job, stage }: { job: Job; stage: Stage }) {
  const metrics = Object.entries(stage.metrics ?? {}).filter(([, v]) => typeof v !== 'object' || v === null)
  const nested = Object.entries(stage.metrics ?? {}).filter(([, v]) => v && typeof v === 'object')
  const stageEvents = job.events.filter((e) => e.stage === stage.id && e.level !== 'info')

  return (
    <div className="panel-body">
      <h3 style={{ fontSize: 16, marginBottom: 4 }}>{stage.name}</h3>
      <p className="muted" style={{ marginTop: 0 }}>{stage.description}</p>
      {stage.status === 'pending' && <p className="muted">Waiting for earlier steps.</p>}
      {stage.status === 'running' && <p>Working on it…</p>}
      {stage.summary && <p><strong>{stage.summary}</strong></p>}
      {stageEvents.map((e, i) => (
        <div key={i} className="notice">
          <strong>{e.code}:</strong> {e.message}
          {e.action && <div>→ {e.action}</div>}
        </div>
      ))}
      <div className={stage.preview ? 'stage-preview' : ''}>
        {stage.preview && <img src={fileUrl(job.id, stage.preview)} alt={`${stage.name} preview`} />}
        <div>
          {metrics.length > 0 && (
            <dl className="metrics">
              {metrics.map(([k, v]) => (
                <div key={k} style={{ display: 'contents' }}>
                  <dt>{label(k)}</dt>
                  <dd>{fmt(v)}</dd>
                </div>
              ))}
            </dl>
          )}
          {nested.map(([k, v]) => (
            <div key={k} style={{ marginTop: 10 }}>
              <div className="small muted" style={{ fontWeight: 600 }}>{label(k)}</div>
              <div className="small">{fmt(v)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
