import { useEffect, useState } from 'react'
import { api, fileUrl } from '../api'
import EventLog from '../components/EventLog'
import { ExportsView, QualityView, SourcesView } from '../components/InfoViews'
import MapView, { type MapFocus } from '../components/MapView'
import StageDetail from '../components/StageDetail'
import StatsView from '../components/StatsView'
import StatusChip from '../components/StatusChip'
import Stepper from '../components/Stepper'
import TreeTable from '../components/TreeTable'
import type { Job } from '../types'

type Tab = 'map' | 'stats' | 'trees' | 'quality' | 'sources' | 'exports' | 'step'

const TABS: { id: Tab; label: string }[] = [
  { id: 'map', label: 'Map' },
  { id: 'stats', label: 'Overview' },
  { id: 'trees', label: 'Trees' },
  { id: 'quality', label: 'Quality' },
  { id: 'exports', label: 'Downloads' },
  { id: 'sources', label: 'Sources' },
  { id: 'step', label: 'Processing' },
]

export default function JobPage({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('step')
  const [selected, setSelected] = useState<string | null>(null)
  const [focus, setFocus] = useState<MapFocus | null>(null)
  // Create the map only once its tab has been shown, so it starts with real dimensions.
  const [mapSeen, setMapSeen] = useState(false)
  useEffect(() => {
    if (tab === 'map') setMapSeen(true)
  }, [tab])

  useEffect(() => {
    let timer: number | undefined
    let alive = true
    const poll = async () => {
      try {
        const j = await api.job(jobId)
        if (!alive) return
        setJob(j)
        if (j.status === 'queued' || j.status === 'running') {
          timer = window.setTimeout(poll, 800)
        }
      } catch (e) {
        if (alive) setError((e as Error).message)
      }
    }
    poll()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [jobId])

  const running = job?.status === 'queued' || job?.status === 'running'
  const completed = job?.status === 'completed'

  // Follow the running stage; switch to the map once complete (unless the user picked a tab).
  useEffect(() => {
    if (!job) return
    if (running) {
      const cur = job.stages.find((s) => s.status === 'running') ?? [...job.stages].reverse().find((s) => s.status === 'done')
      if (cur) setSelected(cur.id)
    }
  }, [job, running])
  const [autoSwitched, setAutoSwitched] = useState(false)
  useEffect(() => {
    if (completed && !autoSwitched) {
      setTab('map')
      setAutoSwitched(true)
    }
  }, [completed, autoSwitched])

  if (error) return <main className="page"><div className="error-box">{error}</div></main>
  if (!job) return <main className="page muted">Loading…</main>

  const done = job.stages.filter((s) => s.status === 'done' || s.status === 'skipped').length
  const stage = job.stages.find((s) => s.id === selected) ?? job.stages[0]
  const visibleTabs = completed ? TABS : TABS.filter((t) => t.id === 'step')

  return (
    <main className="page">
      <nav className="crumbs"><a href="#/">Assessments</a><span>/</span>{job.name}</nav>
      <div className="job-header">
        <div className="job-title">
          <h1>{job.name}</h1>
          <div className="job-meta">
            <StatusChip status={job.status} />
            <span className="chip chip-neutral">{job.mode === 'survey' ? 'Drone survey' : 'Satellite'}</span>
            {job.aoi && <span className="muted">{job.aoi.area_ha.toLocaleString()} ha</span>}
            {job.event_counts.warning > 0 && (
              <span className="chip chip-warning">{job.event_counts.warning} warning{job.event_counts.warning === 1 ? '' : 's'}</span>
            )}
            {job.event_counts.error > 0 && (
              <span className="chip chip-error">{job.event_counts.error} error{job.event_counts.error === 1 ? '' : 's'}</span>
            )}
          </div>
        </div>
        {completed && (
          <div className="job-actions">
            {job.outputs.exports.pdf && (
              <a className="btn btn-primary" href={fileUrl(job.id, job.outputs.exports.pdf.file, true)} download>
                Download report
              </a>
            )}
          </div>
        )}
      </div>

      <div className="job-layout">
        <aside className="side">
          <div className="panel">
            <div className="panel-head">
              <h2>Steps</h2>
              <span className="muted small" style={{ marginLeft: 'auto' }}>{done}/{job.stages.length}</span>
            </div>
            <Stepper
              stages={job.stages}
              selected={tab === 'step' ? stage.id : null}
              onSelect={(id) => {
                setSelected(id)
                setTab('step')
              }}
            />
          </div>
        </aside>

        <section className="panel" style={{ minWidth: 0 }}>
          {running && (
            <div className="progress-hero">
              <strong>Assessment running: {job.stages.find((s) => s.status === 'running')?.name ?? 'starting'}…</strong>
              <div className="progress-bar"><div style={{ width: `${(done / job.stages.length) * 100}%` }} /></div>
              <span className="muted small">Step {Math.min(done + 1, job.stages.length)} of {job.stages.length}</span>
            </div>
          )}
          {job.status === 'failed' && (
            <div className="panel-body">
              <div className="error-box">
                The assessment stopped: {job.stages.find((s) => s.status === 'failed')?.summary ?? 'see the event log'}
              </div>
            </div>
          )}
          {visibleTabs.length > 1 && (
            <nav className="tabs">
              {visibleTabs.map((t) => (
                <button key={t.id} className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)}>
                  {t.label}
                </button>
              ))}
            </nav>
          )}
          {completed && mapSeen && (
            <div style={{ display: tab === 'map' ? 'block' : 'none' }}>
              <MapView job={job} focus={focus} visible={tab === 'map'} />
            </div>
          )}
          {tab === 'stats' && completed && <StatsView job={job} />}
          {tab === 'trees' && completed && (
            <TreeTable
              job={job}
              onLocate={(t) => {
                setFocus({ treeId: t.tree_id, lon: t.longitude, lat: t.latitude, key: Date.now() })
                setTab('map')
              }}
            />
          )}
          {tab === 'quality' && completed && <QualityView job={job} />}
          {tab === 'sources' && completed && <SourcesView job={job} />}
          {tab === 'exports' && completed && <ExportsView job={job} />}
          {(tab === 'step' || !completed) && (
            <>
              <StageDetail job={job} stage={stage} />
              <div className="panel-body log-wrap"><EventLog events={job.events} stages={job.stages} /></div>
            </>
          )}
        </section>
      </div>
    </main>
  )
}
