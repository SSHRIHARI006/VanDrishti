import { fileUrl } from '../api'
import type { Job } from '../types'

export function QualityView({ job }: { job: Job }) {
  const issues = job.events.filter((e) => e.level !== 'info')
  return (
    <div className="panel-body">
      <h3 style={{ fontSize: 15, marginBottom: 8 }}>Rare events and data issues ({issues.length})</h3>
      {issues.length === 0 ? (
        <p className="muted">No warnings or errors during this run.</p>
      ) : (
        <table className="data-table">
          <thead><tr><th>Level</th><th>Event</th><th>What happened</th><th>Action taken / recommended</th></tr></thead>
          <tbody>
            {issues.map((e, i) => (
              <tr key={i}>
                <td><span className={`chip chip-${e.level}`}>{e.level}</span></td>
                <td className="event-code">{e.code}</td>
                <td>{e.message}</td>
                <td>{e.action ?? '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="small muted" style={{ marginTop: 14 }}>
        Tree-level flags (e.g. <code>height_outlier</code> for trees above 40 m) are listed in the inventory for field
        verification. {job.summary.quality?.flagged_trees ?? 0} trees flagged in this run.
      </p>
    </div>
  )
}

export function SourcesView({ job }: { job: Job }) {
  return (
    <div className="panel-body">
      <table className="data-table">
        <thead><tr><th>Dataset</th><th>Resolution</th><th>Licence</th><th>Notes</th></tr></thead>
        <tbody>
          {job.provenance.map((p) => (
            <tr key={p.dataset}>
              <td><strong>{p.dataset}</strong><div className="event-code">{p.source}</div></td>
              <td>{p.resolution_m ? `${p.resolution_m} m` : "–"}</td>
              <td>{p.license}</td>
              <td>{p.notes} {p.period ? `Period: ${p.period}.` : ''} {p.scenes ? `${p.scenes} scenes.` : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small muted" style={{ marginTop: 12 }}>
        All layers are fetched for this boundary only, on the local UTM grid (EPSG:{job.aoi?.utm_epsg}), so areas and
        distances are computed in metres.
      </p>
    </div>
  )
}

export function ExportsView({ job }: { job: Job }) {
  const order = ['pdf', 'csv', 'kmz', 'shapefile', 'geojson', 'chm_tif']
  const items = order.filter((k) => job.outputs.exports[k])
  return (
    <div className="panel-body">
      <div className="export-grid">
        {items.map((k) => {
          const e = job.outputs.exports[k]
          return (
            <a key={k} className="export-card" href={fileUrl(job.id, e.file, true)} download>
              <span className="fmt">{e.label}</span>
              <span className="small muted">Download</span>
            </a>
          )
        })}
      </div>
    </div>
  )
}
